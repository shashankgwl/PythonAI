from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from types import SimpleNamespace

from src.browser_use_step import run_browser_use_summary
from src.config import Settings, load_prompt, load_scenarios
from src.live_progress import LiveProgress
from src.mcp_checks import run_mcp_check
from src.reporting import write_reports


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "scenario"


def _extract_first_url(text: str | None) -> str:
    if not text:
        return ""
    match = re.search(r"https?://[^\s\"'>]+", text)
    return match.group(0).strip() if match else ""


async def run() -> int:
    settings = Settings()
    print("Runner build: 2026-03-22-manual-login-handoff-v1")
    scenarios = load_scenarios(settings.scenario_file)
    global_prompt = load_prompt(settings.prompt_file)

    results: list[dict] = []

    for scenario in scenarios:
        name = scenario.get("name", "Unnamed scenario")
        slug = _slugify(name)
        url = scenario.get("url")
        expected_text = scenario.get("expected_text", "")
        scenario_prompt = scenario.get("prompt")
        requires_mfa = bool(scenario.get("requires_mfa", False))
        mfa_timeout_seconds = int(scenario.get("mfa_timeout_seconds", settings.mfa_timeout_seconds))
        prompt = scenario_prompt or global_prompt
        prompt_url = _extract_first_url(prompt)
        effective_url = url
        if prompt_url and (not url or "main.aspx?appid=" in prompt_url):
            effective_url = prompt_url
            live_note = f"Using URL from prompt: {effective_url}"
        else:
            live_note = f"Using URL from scenario: {effective_url}"
        username = scenario.get("username", settings.test_username)
        password = scenario.get("password", settings.test_password)
        live = LiveProgress(settings.report_dir, name, slug)
        live.add_event("running", "Starting scenario execution.")
        live.add_event("running", live_note)

        if not effective_url:
            live.add_event("failed", "Scenario is missing URL.")
            results.append(
                {
                    "name": name,
                    "url": "",
                    "overall_status": "failed",
                    "error": "Missing 'url' in scenario.",
                }
            )
            continue

        scenario_start = datetime.now(timezone.utc)

        try:
            mcp_result = await run_mcp_check(
                mcp_url=settings.mcp_url,
                url=effective_url,
                expected_text=expected_text,
                timeout_seconds=settings.timeout_seconds,
                report_dir=settings.report_dir,
                scenario_slug=slug,
                requires_mfa=requires_mfa,
                mfa_code_file=settings.mfa_code_file,
                mfa_timeout_seconds=mfa_timeout_seconds,
                username=username,
                password=password,
                page_settle_seconds=settings.page_settle_seconds,
                test_goal=prompt or f"Open {effective_url} and verify expected behavior.",
                agent_max_steps=settings.agent_max_steps,
                manual_login_handoff=settings.manual_login_handoff,
                manual_login_timeout_seconds=settings.manual_login_timeout_seconds,
                progress_cb=live.add_event,
            )
        except Exception as exc:
            mcp_result = None
            mcp_error = str(exc)
            live.add_event("failed", f"MCP check failed: {mcp_error}")

        if settings.run_browser_use:
            live.add_event("running", "Starting browser-use prompt execution.")
            browser_use_result = await run_browser_use_summary(effective_url, prompt=prompt)
            live.add_event(browser_use_result.status if browser_use_result.status in {"passed", "failed"} else "running", browser_use_result.summary)
        else:
            browser_use_result = SimpleNamespace(
                status="skipped",
                summary="Skipped because RUN_BROWSER_USE=false (default for stable MCP-only flow).",
                duration_seconds=0.0,
            )
            live.add_event("running", browser_use_result.summary)

        scenario_end = datetime.now(timezone.utc)
        total_duration = (scenario_end - scenario_start).total_seconds()

        if mcp_result is None:
            overall_status = "failed"
            mcp_section = {
                "status": "failed",
                "details": mcp_error,
                "snapshot_excerpt": "",
                "duration_seconds": 0,
                "tool_count": 0,
            }
        else:
            overall_status = "passed" if mcp_result.passed else "failed"
            mcp_section = {
                "status": "passed" if mcp_result.passed else "failed",
                "details": mcp_result.details,
                "snapshot_excerpt": mcp_result.snapshot_excerpt,
                "duration_seconds": mcp_result.duration_seconds,
                "tool_count": mcp_result.tool_count,
            }

        live.add_event(overall_status, f"Scenario finished in {total_duration:.2f}s.")

        results.append(
            {
                "name": name,
                "url": effective_url,
                "expected_text": expected_text,
                "requires_mfa": requires_mfa,
                "prompt": prompt or "",
                "overall_status": overall_status,
                "duration_seconds": total_duration,
                "mcp": mcp_section,
                "browser_use": {
                    "status": browser_use_result.status,
                    "summary": browser_use_result.summary,
                    "duration_seconds": browser_use_result.duration_seconds,
                },
            }
        )

    written = write_reports(results, settings.report_dir, settings.template_path)

    print(f"Report JSON: {written['json']}")
    print(f"Report HTML: {written['html']}")

    failed = any(r.get("overall_status") != "passed" for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
