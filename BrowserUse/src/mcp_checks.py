from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from mcp import ClientSession
from mcp.client.sse import sse_client


@dataclass
class MCPCheckResult:
    passed: bool
    details: str
    snapshot_excerpt: str
    duration_seconds: float
    tool_count: int


@dataclass
class PlannerContext:
    goal: str
    expected_text: str
    username: str
    password: str
    mfa_hint: str
    objectives: list[str]


def _planner_trace_path(report_dir: Path) -> Path:
    return Path(os.getenv("PLANNER_TRACE_FILE", str(report_dir / "planner_trace.jsonl")))


def _planner_trace_enabled() -> bool:
    return os.getenv("PLANNER_TRACE_ENABLED", "true").lower() in {"1", "true", "yes", "on"}


def _append_planner_trace(report_dir: Path, payload: dict[str, Any]) -> None:
    if not _planner_trace_enabled():
        return
    path = _planner_trace_path(report_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(payload)
    row["ts"] = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _extract_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return " ".join(_extract_text(v) for v in payload.values())
    if isinstance(payload, list):
        return " ".join(_extract_text(v) for v in payload)

    content = getattr(payload, "content", None)
    if content is not None:
        return _extract_text(content)

    text = getattr(payload, "text", None)
    if isinstance(text, str):
        return text

    try:
        return json.dumps(payload, default=str)
    except Exception:
        return str(payload)


def _extract_image_bytes(payload: Any) -> bytes | None:
    if payload is None:
        return None
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if isinstance(payload, str):
        return None
    if isinstance(payload, dict):
        data = payload.get("data")
        mime = str(payload.get("mimeType", payload.get("mime_type", ""))).lower()
        if isinstance(data, str) and ("image/" in mime or payload.get("type") == "image"):
            try:
                return base64.b64decode(data)
            except Exception:
                return None
        for value in payload.values():
            found = _extract_image_bytes(value)
            if found:
                return found
        return None
    if isinstance(payload, list):
        for item in payload:
            found = _extract_image_bytes(item)
            if found:
                return found
        return None

    content = getattr(payload, "content", None)
    if content is not None:
        found = _extract_image_bytes(content)
        if found:
            return found

    data_attr = getattr(payload, "data", None)
    mime_attr = str(getattr(payload, "mimeType", getattr(payload, "mime_type", ""))).lower()
    if isinstance(data_attr, str) and "image/" in mime_attr:
        try:
            return base64.b64decode(data_attr)
        except Exception:
            return None

    if hasattr(payload, "__dict__"):
        return _extract_image_bytes(vars(payload))
    return None


def _emit(progress_cb: Callable[[str, str, str | None], None] | None, status: str, message: str, screenshot: str | None = None) -> None:
    if progress_cb:
        progress_cb(status, message, screenshot)


def _normalize_azure_endpoint(raw: str | None) -> str | None:
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    return f"{parsed.scheme}://{parsed.netloc}/"


def _to_sse_url(mcp_url: str) -> str:
    if mcp_url.endswith("/mcp"):
        return f"{mcp_url[:-4]}/sse"
    if mcp_url.endswith("/"):
        return f"{mcp_url}sse"
    return f"{mcp_url}/sse"


def _build_llm_client() -> tuple[Any, str]:
    openai_module = importlib.import_module("openai")
    AzureOpenAI = getattr(openai_module, "AzureOpenAI")
    OpenAI = getattr(openai_module, "OpenAI")

    azure_endpoint = _normalize_azure_endpoint(os.getenv("AZURE_OPENAI_ENDPOINT"))
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    if azure_endpoint and azure_key and azure_deployment:
        client = AzureOpenAI(
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            azure_endpoint=azure_endpoint,
            api_key=azure_key,
        )
        return client, azure_deployment

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        client = OpenAI(api_key=openai_key)
        return client, os.getenv("OPENAI_MODEL", "gpt-5-mini")

    raise RuntimeError(
        "No LLM credentials configured. Set Azure vars (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, "
        "AZURE_OPENAI_DEPLOYMENT_NAME) or OPENAI_API_KEY for autonomous MCP mode."
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"Planner did not return JSON: {text[:300]}")
    return json.loads(text[start : end + 1])


def _read_mfa_code(mfa_code_file: Path) -> str:
    if not mfa_code_file.exists():
        return ""
    raw = mfa_code_file.read_text(encoding="utf-8")
    for line in raw.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.lower() in {"approved", "continue", "done"}:
            return value
        if re.fullmatch(r"[A-Za-z0-9_-]{4,12}", value):
            return value
    return ""


def _extract_objectives(goal: str) -> list[str]:
    lines = [ln.strip(" -\t\r") for ln in (goal or "").splitlines()]
    objectives: list[str] = []
    skip_phrases = [
        "enter username:",
        "enter password:",
        "if mfa",
        "mfa",
        "verification code",
        "approve sign in",
        "you must",
        "wait for the page to load fully",
        "wait for full load",
        "you are starting after user login is complete",
        "execute these steps in order",
        "do not finish early",
        "finish only after",
    ]
    for line in lines:
        if not line:
            continue
        normalized = re.sub(r"^\d+\.\s*", "", line).strip()
        low = normalized.lower()
        if any(p in low for p in skip_phrases):
            continue
        # Standalone screenshot directives without a target cause loops.
        if low in {"capture screenshot", "take screenshot"}:
            continue
        if len(normalized) < 8:
            continue
        objectives.append(normalized)
    if not objectives and goal:
        objectives.append("Complete the remaining post-login navigation tasks in the prompt.")
    return objectives[:12]


def _is_auth_objective_line(line: str) -> bool:
    low = (line or "").lower()
    auth_markers = [
        "enter username",
        "enter password",
        "mfa",
        "verification code",
        "approve sign in",
        "pick an account",
        "stay signed in",
        "don't show again",
    ]
    return any(m in low for m in auth_markers)


def _extract_post_auth_objectives(goal: str) -> list[str]:
    all_objectives = _extract_objectives(goal)
    post = [o for o in all_objectives if not _is_auth_objective_line(o)]
    return post or all_objectives


def _objective_tokens(objective: str) -> set[str]:
    stop = {
        "the", "and", "then", "with", "that", "this", "from", "your", "into",
        "page", "wait", "load", "click", "open", "take", "screenshot", "now",
        "once", "after", "full", "for", "you", "see", "if", "on", "to", "a",
    }
    words = re.findall(r"[a-z0-9]+", objective.lower())
    tokens = {w for w in words if len(w) >= 3 and w not in stop}
    expanded = set(tokens)
    if "side" in tokens or "panel" in tokens:
        expanded.update({"site", "map", "navigation", "menu", "sitemap"})
    if "contact" in tokens or "contacts" in tokens:
        expanded.update({"contact", "contacts"})
    if "create" in tokens or "new" in tokens:
        expanded.update({"new", "create", "add"})
    return expanded


def _update_objective_status(objectives: list[str], status: list[bool], evidence_text: str) -> list[bool]:
    out = list(status)
    evidence = (evidence_text or "").lower()
    for i, obj in enumerate(objectives):
        if out[i]:
            continue
        tokens = _objective_tokens(obj)
        if not tokens:
            continue
        hits = sum(1 for t in tokens if t in evidence)
        threshold = 2 if len(tokens) >= 3 else 1
        if hits >= threshold:
            out[i] = True
    return out


def _next_pending_objective(objectives: list[str], status: list[bool]) -> str:
    for i, obj in enumerate(objectives):
        if i >= len(status) or not status[i]:
            return obj
    return ""


def _objective_done_map(objectives: list[str], status: list[bool]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for i, obj in enumerate(objectives):
        out[(obj or "").lower()] = bool(i < len(status) and status[i])
    return out


def _reconcile_objective_status(
    objectives: list[str],
    status: list[bool],
    snapshot_text: str,
) -> list[bool]:
    out = list(status)
    if not objectives:
        return out

    snapshot = (snapshot_text or "").lower()
    done_map = _objective_done_map(objectives, out)

    def _is_done_contains(*parts: str) -> bool:
        for objective_text, is_done in done_map.items():
            if not is_done:
                continue
            if all(p in objective_text for p in parts):
                return True
        return False

    for idx, obj in enumerate(objectives):
        if idx < len(out) and out[idx]:
            continue
        low = (obj or "").lower()

        # If downstream objectives are completed, infer prerequisites were completed.
        if ("side panel" in low or "site map" in low) and _is_done_contains("click", "contacts"):
            out[idx] = True
            continue
        if "click contacts" in low and (
            _is_done_contains("contacts", "grid")
            or _is_done_contains("new", "contact", "form")
            or _is_done_contains("fill", "contact", "form")
        ):
            out[idx] = True
            continue
        if "click new" in low and (
            _is_done_contains("new", "contact", "form")
            or _is_done_contains("fill", "contact", "form")
            or _is_done_contains("click save")
        ):
            out[idx] = True
            continue

        # Strong snapshot signal for Dataverse side-nav state.
        if ("side panel" in low or "site map" in low) and "button \"site map\" [expanded]" in snapshot:
            out[idx] = True

    return out


def _is_page_load_objective(text: str) -> bool:
    s = (text or "").lower()
    markers = [
        "ensure page is fully loaded",
        "wait for full load",
        "wait for the page to load",
        "page is fully loaded",
        "confirm page is loaded",
    ]
    return any(m in s for m in markers)


def _is_screenshot_objective(text: str) -> bool:
    s = (text or "").lower()
    return "screenshot" in s or "screen shot" in s


def _normalize_ref_value(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.lower().startswith("ref="):
        return raw.split("=", 1)[1].strip()
    return raw


def _is_validation_error_text(text: str) -> bool:
    low = (text or "").lower()
    return "invalid_type" in low and "\"message\": \"required\"" in low


async def _take_screenshot(
    session: ClientSession,
    tool_names: set[str],
    report_dir: Path,
    scenario_slug: str,
    suffix: str,
    progress_cb: Callable[[str, str, str | None], None] | None = None,
) -> str | None:
    if "browser_take_screenshot" not in tool_names:
        return None

    screenshots_dir = report_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{scenario_slug}-{suffix}.png"
    rel_path = f"screenshots/{filename}"
    abs_path = str((report_dir / rel_path).resolve())

    call_attempts = [abs_path, rel_path]
    last_error: str | None = None
    for filename_arg in call_attempts:
        try:
            result = await session.call_tool(
                "browser_take_screenshot",
                {"filename": filename_arg, "fullPage": True, "type": "png"},
            )
            target_file = report_dir / rel_path
            if target_file.exists() and target_file.stat().st_size > 0:
                return rel_path

            image_bytes = _extract_image_bytes(result)
            if image_bytes:
                target_file.write_bytes(image_bytes)
                return rel_path
            last_error = f"No file/image bytes returned for filename={filename_arg}"
        except Exception as exc:
            last_error = str(exc)

    _emit(progress_cb, "running", f"Screenshot capture failed: {last_error or 'unknown error'}")
    return None


def _build_system_prompt(tools: set[str]) -> str:
    return (
        "You are an autonomous web testing controller operating Playwright MCP tools. "
        "Return ONLY a valid JSON object with one of these actions: "
        "{'action':'tool','tool_name':'<name>','arguments':{...},'message':'...'} OR "
        "{'action':'await_human_code','message':'...'} OR "
        "{'action':'finish','success':true/false,'message':'...'} . "
        "Only use tool_name from available tools. Keep arguments minimal and valid. "
        "Prefer browser_snapshot-guided refs for interactions. "
        "Prefer click + type + press Enter flow over repeated browser_fill_form on login pages. "
        "When login/password fields are visible, prioritize entering credentials if provided in the prompt context. "
        "When an MFA challenge appears, use await_human_code action. "
        "If same screen repeats, change strategy (different click target or keypress) instead of repeating identical action. "
        "Primary page-readiness signal is URL/path + document.readyState, not exact title text. "
        "Avoid brittle waits on exact branded text when URL indicates target app is loaded. "
        "Treat expected text as only a checkpoint, not completion, unless the goal itself is only that check. "
        "Do not finish immediately after login/home load when the goal includes additional actions. "
        "For multi-step goals, continue until all requested actions are performed. "
        f"Available tools: {sorted(tools)}"
    )


def _build_user_prompt(
    context: PlannerContext,
    snapshot_text: str,
    history: list[str],
    step: int,
    max_steps: int,
    stuck_count: int,
    objective_status: list[bool],
    next_objective: str,
    target_page_loaded: bool,
) -> str:
    cred_info = "Credentials unavailable."
    if context.username and context.password:
        cred_info = (
            "Credentials available for use:\n"
            f"- username: {context.username}\n"
            f"- password: {context.password}"
        )

    recent_history = "\n".join(history[-8:]) if history else "(none yet)"
    truncated_snapshot = snapshot_text[:7000]
    objective_lines = []
    for idx, obj in enumerate(context.objectives):
        mark = "done" if (idx < len(objective_status) and objective_status[idx]) else "pending"
        objective_lines.append(f"{idx + 1}. [{mark}] {obj}")
    objective_block = "\n".join(objective_lines) if objective_lines else "(none)"

    anti_loop_hint = ""
    if stuck_count >= 2:
        anti_loop_hint = (
            "The screen appears unchanged for multiple steps. "
            "Do NOT repeat the same fill/type action. "
            "Choose a transition action now: click a Next/Sign in/Continue button by ref, "
            "or press Enter after focusing the active input."
        )

    return (
        f"Goal:\n{context.goal}\n\n"
        f"Immediate target objective: {next_objective or '(all done)'}\n\n"
        f"Target URL loaded by URL/path check: {'yes' if target_page_loaded else 'no'}\n"
        f"Expected text to verify: {context.expected_text or '(none)'}\n"
        f"MFA instructions: {context.mfa_hint}\n"
        f"Step: {step}/{max_steps}\n\n"
        f"Repeated-same-screen count: {stuck_count}\n\n"
        f"Anti-loop guidance: {anti_loop_hint or 'N/A'}\n\n"
        f"Objectives:\n{objective_block}\n\n"
        f"{cred_info}\n\n"
        f"Recent actions:\n{recent_history}\n\n"
        f"Current page snapshot:\n{truncated_snapshot}\n\n"
        "Decide the best single next action."
    )


def _plan_next_action(
    planner_client: Any,
    model: str,
    tools: set[str],
    context: PlannerContext,
    snapshot_text: str,
    history: list[str],
    step: int,
    max_steps: int,
    stuck_count: int,
    objective_status: list[bool],
    next_objective: str,
    target_page_loaded: bool,
    report_dir: Path,
) -> dict[str, Any]:
    system_prompt = _build_system_prompt(tools)
    user_prompt = _build_user_prompt(
        context=context,
        snapshot_text=snapshot_text,
        history=history,
        step=step,
        max_steps=max_steps,
        stuck_count=stuck_count,
        objective_status=objective_status,
        next_objective=next_objective,
        target_page_loaded=target_page_loaded,
    )
    _append_planner_trace(
        report_dir,
        {
            "kind": "planner_request",
            "step": step,
            "model": model,
            "next_objective": next_objective,
            "target_page_loaded": target_page_loaded,
            "stuck_count": stuck_count,
            "history_tail": history[-6:],
            "snapshot_preview": snapshot_text[:1800],
            "system_prompt_preview": system_prompt[:1200],
            "user_prompt_preview": user_prompt[:2400],
        },
    )
    response = planner_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    action = _extract_json_object(content)
    _append_planner_trace(
        report_dir,
        {
            "kind": "planner_response",
            "step": step,
            "raw_content": content[:5000],
            "parsed_action": action,
        },
    )
    return action


def _looks_like_auth_step(snapshot_text: str) -> bool:
    s = (snapshot_text or "").lower()
    auth_markers = [
        "sign in",
        "enter your email",
        "email, phone, or skype",
        "enter password",
        "password",
        "pick an account",
        "stay signed in",
        "continue",
        "next",
    ]
    return any(m in s for m in auth_markers)


async def _wait_for_mfa_code(
    session: ClientSession,
    tool_names: set[str],
    mfa_code_file: Path,
    timeout_seconds: int,
    report_dir: Path,
    scenario_slug: str,
    progress_cb: Callable[[str, str, str | None], None] | None,
) -> bool:
    _emit(progress_cb, "waiting_mfa", f"Waiting for MFA code in {mfa_code_file}. Enter code and save file.")

    elapsed = 0
    mfa_not_visible_streak = 0
    while elapsed < timeout_seconds:
        await asyncio.sleep(2)
        elapsed += 2

        if elapsed % 6 == 0:
            mfa_poll_shot = await _take_screenshot(
                session,
                tool_names,
                report_dir,
                scenario_slug,
                f"mfa-wait-{elapsed}",
                progress_cb=progress_cb,
            )
            if mfa_poll_shot:
                _emit(progress_cb, "waiting_mfa", "Captured updated MFA screenshot.", mfa_poll_shot)

        mfa_visible = await _is_mfa_ui_visible(session, tool_names)
        if not mfa_visible:
            mfa_not_visible_streak += 1
            if mfa_not_visible_streak >= 2:
                _emit(progress_cb, "running", "MFA screen is no longer visible; continuing test flow.")
                return True
        else:
            mfa_not_visible_streak = 0

        code = _read_mfa_code(mfa_code_file)
        if not code:
            continue

        if code.lower() in {"approved", "continue", "done"}:
            mfa_code_file.write_text("", encoding="utf-8")
            _emit(progress_cb, "running", "Human approved MFA. Continuing test flow.")
            return True

        if "browser_type" not in tool_names:
            _emit(progress_cb, "failed", "MFA code provided, but browser_type tool is unavailable.")
            return False

        if "browser_evaluate" in tool_names:
            await session.call_tool(
                "browser_evaluate",
                {
                    "function": """
() => {
  const selectors = [
    'input[type="tel"]',
    'input[type="number"]',
    'input[name*="otp" i]',
    'input[name*="code" i]',
    'input[id*="otp" i]',
    'input[id*="code" i]'
  ];
  const target = selectors.map(s => document.querySelector(s)).find(Boolean) || document.activeElement;
  if (target && typeof target.focus === 'function') target.focus();
  return !!target;
}
""",
                },
            )

        await session.call_tool("browser_type", {"text": code})
        if "browser_press_key" in tool_names:
            await session.call_tool("browser_press_key", {"key": "Enter"})

        mfa_code_file.write_text("", encoding="utf-8")
        _emit(progress_cb, "running", "MFA code submitted to browser.")
        return True

    _emit(progress_cb, "failed", f"Timed out waiting for MFA code after {timeout_seconds}s.")
    return False


async def _execute_tool_action(
    session: ClientSession,
    tool_names: set[str],
    action: dict[str, Any],
    report_dir: Path,
    scenario_slug: str,
    step: int,
    progress_cb: Callable[[str, str, str | None], None] | None,
) -> tuple[str, str]:
    tool_name = str(action.get("tool_name", "")).strip()
    args = action.get("arguments", {}) or {}

    if tool_name not in tool_names:
        return "", f"Planner requested unavailable tool: {tool_name}"

    if tool_name == "browser_take_screenshot" and "filename" not in args:
        args = dict(args)
        args["filename"] = f"screenshots/{scenario_slug}-step-{step}.png"
        args.setdefault("type", "png")
    if tool_name == "browser_wait_for":
        args = dict(args)
        if "text" not in args and "selector" in args:
            selector = str(args.get("selector", "")).strip()
            if selector.lower().startswith("text="):
                args["text"] = selector.split("=", 1)[1].strip().strip("'\"")
        if "time" not in args and "timeout" in args:
            try:
                timeout_raw = float(args.get("timeout"))
                # planner often sends ms; tool expects seconds
                args["time"] = max(1, int(timeout_raw / 1000)) if timeout_raw > 100 else int(timeout_raw)
            except Exception:
                args["time"] = 3
        if not any(k in args for k in ("time", "text", "textGone")):
            args["time"] = 3

    attempts: list[dict[str, Any]] = [dict(args)]
    if tool_name == "browser_click":
        if "ref" in args and "element" not in args:
            attempts.append({**dict(args), "element": _normalize_ref_value(args.get("ref"))})
        if "element" in args and "ref" not in args:
            attempts.append({**dict(args), "ref": _normalize_ref_value(args.get("element"))})
    if tool_name == "browser_type":
        if "element" in args and "ref" not in args:
            attempts.append({**dict(args), "ref": _normalize_ref_value(args.get("element"))})
        if "ref" in args and "element" not in args:
            attempts.append({**dict(args), "element": _normalize_ref_value(args.get("ref"))})

    last_result_text = ""
    for idx, attempt_args in enumerate(attempts, start=1):
        _emit(progress_cb, "running", f"Executing tool: {tool_name}")
        _append_planner_trace(
            report_dir,
            {
                "kind": "tool_execute",
                "step": step,
                "tool_name": tool_name,
                "arguments": attempt_args,
                "attempt": idx,
            },
        )
        result = await session.call_tool(tool_name, attempt_args)
        result_text = _extract_text(result)
        last_result_text = result_text
        _append_planner_trace(
            report_dir,
            {
                "kind": "tool_result",
                "step": step,
                "tool_name": tool_name,
                "result_preview": result_text[:3000],
                "attempt": idx,
            },
        )

        # Retry once with alternate key shape if MCP reports schema mismatch.
        if _is_validation_error_text(result_text) and idx < len(attempts):
            _emit(progress_cb, "running", f"{tool_name} schema mismatch, retrying with alternate arguments.")
            continue

        args = attempt_args
        break

    shot = None
    if tool_name == "browser_take_screenshot":
        filename = str(args.get("filename", ""))
        if filename.startswith("screenshots/"):
            shot = filename

    if _is_validation_error_text(last_result_text):
        return "", f"Tool {tool_name} validation error: {last_result_text[:220]}"

    if shot:
        _emit(progress_cb, "running", f"Tool {tool_name} completed.", shot)
    else:
        _emit(progress_cb, "running", f"Tool {tool_name} completed.")

    return last_result_text, ""


async def _is_mfa_ui_visible(session: ClientSession, tool_names: set[str]) -> bool:
    if "browser_evaluate" not in tool_names:
        return False
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": """
() => {
  const pageText = (document.body?.innerText || '').toLowerCase();
  const hasOtpInput = !!document.querySelector(
    'input[type="tel"],input[type="number"],input[name*="otp" i],input[name*="code" i],input[id*="otp" i],input[id*="code" i]'
  );
  const mfaKeywords = ['verification code','enter code','approve sign in','authenticator','security code','two-step'];
  const hasKeyword = mfaKeywords.some(k => pageText.includes(k));
  return hasOtpInput || hasKeyword;
}
""",
        },
    )
    text = _extract_text(result).strip().lower()
    return "true" in text


async def _get_compact_state(session: ClientSession, tool_names: set[str]) -> str:
    if "browser_snapshot" in tool_names:
        snapshot_result = await session.call_tool("browser_snapshot", {})
        return _extract_text(snapshot_result)
    if "browser_evaluate" in tool_names:
        state = await session.call_tool(
            "browser_evaluate",
            {
                "function": """
() => {
  const txt = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
  const visibleInputs = Array.from(document.querySelectorAll('input'))
    .filter(el => {
      const s = window.getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
    })
    .slice(0, 8)
    .map(el => ({
      type: el.type || '',
      name: el.name || '',
      id: el.id || '',
      placeholder: el.placeholder || ''
    }));
  const buttons = Array.from(document.querySelectorAll('button,input[type=\"submit\"]'))
    .slice(0, 8)
    .map(el => (el.innerText || el.value || '').trim())
    .filter(Boolean);
  return {
    url: location.href,
    title: document.title,
    readyState: document.readyState,
    visibleInputs,
    buttons,
    textSample: txt.slice(0, 1800)
  };
}
""",
            },
        )
        return _extract_text(state)
    return "(No snapshot/evaluate tool available)"


async def _fallback_auth_progress(
    session: ClientSession,
    tool_names: set[str],
    username: str,
    password: str,
) -> str:
    if "browser_evaluate" not in tool_names:
        return "no-browser-evaluate"
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": f"""
() => {{
  const setValue = (el, value) => {{
    el.focus();
    el.value = value;
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};

  const userSelectors = [
    'input[type="email"]',
    'input[name*="user" i]',
    'input[name="loginfmt"]',
    'input[id*="user" i]',
    'input[id="i0116"]',
    'input[autocomplete="username"]',
    'input[type="text"]'
  ];
  const passSelectors = [
    'input[type="password"]',
    'input[name*="pass" i]',
    'input[name="passwd"]',
    'input[id*="pass" i]',
    'input[id="i0118"]',
    'input[autocomplete="current-password"]'
  ];
  const clickSubmit = () => {{
    const buttons = Array.from(document.querySelectorAll('button,input[type="submit"],input[type="button"],div[role="button"]'));
    const labels = ['next', 'sign in', 'continue', 'yes', 'submit'];
    for (const lbl of labels) {{
      const el = buttons.find(b => ((b.innerText || b.value || '').trim().toLowerCase().includes(lbl)));
      if (el) {{
        el.click();
        return true;
      }}
    }}
    return false;
  }};

  const pwd = passSelectors.map(s => document.querySelector(s)).find(Boolean);
  if (pwd && {json.dumps(bool(password))}) {{
    setValue(pwd, {json.dumps(password)});
    const clicked = clickSubmit();
    return {{step: 'password', clicked}};
  }}

  const usr = userSelectors.map(s => document.querySelector(s)).find(Boolean);
  if (usr && {json.dumps(bool(username))}) {{
    setValue(usr, {json.dumps(username)});
    const clicked = clickSubmit();
    return {{step: 'username', clicked}};
  }}

  return {{step: 'none', clicked: false}};
}}
""",
        },
    )
    return _extract_text(result)


async def _attempt_objective_progress(
    session: ClientSession,
    tool_names: set[str],
    objective: str,
) -> str:
    if not objective or "browser_evaluate" not in tool_names:
        return "objective-progress-skip"
    tokens = sorted(_objective_tokens(objective))
    token_js = json.dumps(tokens[:6])
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": f"""
() => {{
  const tokens = {token_js};
  if (!tokens.length) return {{clicked:false, reason:'no-tokens'}};
  const candidates = Array.from(document.querySelectorAll('a,button,[role="button"],span,div'));
  const scored = candidates
    .map(el => {{
      const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
      if (!txt) return null;
      const score = tokens.reduce((n, t) => n + (txt.includes(t) ? 1 : 0), 0);
      return score > 0 ? {{el, txt, score}} : null;
    }})
    .filter(Boolean)
    .sort((a, b) => b.score - a.score);
  if (scored.length) {{
    scored[0].el.click();
    return {{clicked:true, text:scored[0].txt.slice(0,120), score:scored[0].score}};
  }}
  return {{clicked:false, reason:'no-match'}};
}}
""",
        },
    )
    return _extract_text(result)


async def _detect_auth_stage(session: ClientSession, tool_names: set[str]) -> dict[str, Any]:
    if "browser_evaluate" not in tool_names:
        return {"stage": "unknown"}
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": """
() => {
  const text = (document.body?.innerText || '').toLowerCase();
  const q = (s) => document.querySelector(s);
  const hasUser = !!(q('input[type="email"]') || q('input[name="loginfmt"]') || q('input[id="i0116"]') || q('input[autocomplete="username"]'));
  const hasPass = !!(q('input[type="password"]') || q('input[name="passwd"]') || q('input[id="i0118"]') || q('input[autocomplete="current-password"]'));
  const pickAccount = text.includes('pick an account');
  const staySignedIn = text.includes('stay signed in');
  const mfaText = ['verification code','approve sign in','authenticator','security code','two-step'].some(k => text.includes(k));
  const mfaInput = !!q('input[type="tel"],input[type="number"],input[name*="otp" i],input[name*="code" i],input[id*="otp" i],input[id*="code" i]');

  if (hasPass) return { stage: 'password' };
  if (hasUser) return { stage: 'username' };
  if (pickAccount) return { stage: 'pick_account' };
  if (staySignedIn) return { stage: 'stay_signed_in' };
  if (mfaText || mfaInput) return { stage: 'mfa' };
  return { stage: 'other', url: location.href, title: document.title };
}
""",
        },
    )
    raw = _extract_text(result)
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start : end + 1])
    except Exception:
        pass
    return {"stage": "unknown", "raw": raw[:300]}


async def _wait_for_manual_login_handoff(
    session: ClientSession,
    tool_names: set[str],
    target_url: str,
    timeout_seconds: int,
    report_dir: Path,
    scenario_slug: str,
    progress_cb: Callable[[str, str, str | None], None] | None,
) -> tuple[bool, str]:
    if "browser_evaluate" not in tool_names:
        _emit(progress_cb, "failed", "Manual login handoff requires browser_evaluate tool.")
        return False, ""

    target = (target_url or "").lower()
    target_host = urlparse(target_url).netloc.lower() if target_url else ""
    target_path = urlparse(target_url).path.lower() if target_url else ""

    def _parse_handoff_state(raw_text: str) -> tuple[str, str, bool]:
        text = raw_text or ""
        # First try strict JSON block parsing.
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                payload = json.loads(text[start : end + 1])
                return (
                    str(payload.get("href", "") or ""),
                    str(payload.get("readyState", "") or ""),
                    bool(payload.get("isReady", False)),
                )
        except Exception:
            pass

        # Fallback for MCP object-like rendering (not strict JSON).
        href = ""
        ready_state = ""
        is_ready = False
        href_match = re.search(r"href\s*[:=]\s*['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
        if href_match:
            href = href_match.group(1).strip()
        ready_match = re.search(r"readyState\s*[:=]\s*['\"]([^'\"]+)['\"]", text, flags=re.IGNORECASE)
        if ready_match:
            ready_state = ready_match.group(1).strip()
        if re.search(r"isReady\s*[:=]\s*true\b", text, flags=re.IGNORECASE):
            is_ready = True
        if not href:
            url_match = re.search(r"https?://[^\s'\"<>]+", text, flags=re.IGNORECASE)
            if url_match:
                href = url_match.group(0).strip()
        if not ready_state:
            ready_match2 = re.search(r"\b(loading|interactive|complete)\b", text, flags=re.IGNORECASE)
            if ready_match2:
                ready_state = ready_match2.group(1)
        return href, ready_state, is_ready

    waited = 0
    while waited < timeout_seconds:
        href_text = ""
        ready_text = ""
        # Primary path: fetch plain values to avoid object parsing edge cases.
        try:
            href_raw = await session.call_tool(
                "browser_evaluate",
                {"function": "() => location.href"},
            )
            href_text = _extract_text(href_raw)
        except Exception:
            href_text = ""

        try:
            ready_raw = await session.call_tool(
                "browser_evaluate",
                {"function": "() => document.readyState"},
            )
            ready_text = _extract_text(ready_raw)
        except Exception:
            ready_text = ""

        result = await session.call_tool(
            "browser_evaluate",
            {
                "function": f"""
() => {{
  const href = (location.href || '').toLowerCase();
  const ready = (document.readyState || '').toLowerCase();
  const hasMain = href.includes('/main.aspx');
  const target = {json.dumps(target)};
  const targetHost = {json.dumps(target_host)};
  const hostMatches = !targetHost || href.includes(targetHost);
  const targetMatches = target ? href.includes(target) : true;
  const loaded = ready === 'complete';
  return JSON.stringify({{
    href: location.href,
    readyState: document.readyState,
    isReady: loaded && hasMain && hostMatches && (targetMatches || hasMain)
  }});
}}
""",
            },
        )
        state_text = _extract_text(result)
        current_url, ready_state, is_ready = _parse_handoff_state(state_text)
        href_plain, _, _ = _parse_handoff_state(href_text)
        _, ready_plain, _ = _parse_handoff_state(ready_text)
        if href_plain:
            current_url = href_plain
        if ready_plain:
            ready_state = ready_plain

        url_lower = (current_url or "").lower()
        ready_lower = (ready_state or "").lower()
        host_ok = (not target_host) or (target_host in url_lower)
        parsed_current = urlparse(current_url or "")
        current_path = (parsed_current.path or "").lower()
        main_ok = current_path.endswith("/main.aspx") or current_path == "/main.aspx"
        # Do not hard-block on readyState because some environments hide/omit it via MCP response formatting.
        if host_ok and main_ok:
            is_ready = True
        elif (
            ready_lower == "complete"
            and host_ok
            and ("dynamics.com" in url_lower)
            and (not target_path or current_path.endswith(target_path))
            and "login.microsoftonline.com" not in (parsed_current.netloc or "").lower()
        ):
            is_ready = True

        if is_ready:
            _emit(progress_cb, "running", f"Manual login handoff complete at URL: {current_url}")
            return True, current_url

        waited += 2
        if waited % 10 == 0:
            shot = await _take_screenshot(
                session,
                tool_names,
                report_dir,
                scenario_slug,
                f"handoff-wait-{waited}",
                progress_cb=progress_cb,
            )
            if shot:
                _emit(
                    progress_cb,
                    "running",
                    f"Waiting for manual login handoff ({waited}s/{timeout_seconds}s). "
                    f"Current readyState={ready_state}, URL={current_url or '(unknown)'}",
                    shot,
                )
            else:
                _emit(
                    progress_cb,
                    "running",
                    f"Waiting for manual login handoff ({waited}s/{timeout_seconds}s). "
                    f"Current readyState={ready_state}, URL={current_url or '(unknown)'}",
                )
        await asyncio.sleep(2)

    _emit(progress_cb, "failed", f"Manual login handoff timed out after {timeout_seconds}s.")
    return False, ""


async def _is_target_url_loaded(session: ClientSession, tool_names: set[str], target_url: str) -> bool:
    if "browser_evaluate" not in tool_names:
        return False
    target_parsed = urlparse(target_url or "")
    target_host = (target_parsed.netloc or "").lower()
    target_path = (target_parsed.path or "").lower()
    try:
        href_raw = await session.call_tool("browser_evaluate", {"function": "() => location.href"})
        ready_raw = await session.call_tool("browser_evaluate", {"function": "() => document.readyState"})
    except Exception:
        return False

    href_text = _extract_text(href_raw).strip().strip("'\"")
    ready_text = _extract_text(ready_raw).strip().strip("'\"").lower()
    parsed = urlparse(href_text)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if not host or not path:
        return False
    if "login.microsoftonline.com" in host:
        return False
    host_ok = (not target_host) or (target_host == host)
    path_ok = (not target_path) or path.endswith(target_path)
    dataverse_ok = "/main.aspx" in path
    return host_ok and path_ok and dataverse_ok and ready_text == "complete"


def _is_target_url_loaded_from_snapshot(snapshot_text: str, target_url: str) -> bool:
    parsed_target = urlparse(target_url or "")
    target_host = (parsed_target.netloc or "").lower()
    m = re.search(r"- Page URL:\s*(\S+)", snapshot_text or "")
    if not m:
        return False
    current_url = m.group(1).strip()
    parsed_current = urlparse(current_url)
    host = (parsed_current.netloc or "").lower()
    path = (parsed_current.path or "").lower()
    if "login.microsoftonline.com" in host:
        return False
    host_ok = (not target_host) or (target_host == host)
    return host_ok and ("/main.aspx" in path)


def _stage_from_snapshot(snapshot_text: str) -> str:
    s = (snapshot_text or "").lower()
    if any(k in s for k in ["enter password", "password for", "input[type=\"password\"]", "i0118"]):
        return "password"
    if any(k in s for k in ["enter your email, phone, or skype", "email, phone, or skype", "loginfmt", "i0116"]):
        return "username"
    if "pick an account" in s:
        return "pick_account"
    if "stay signed in" in s:
        return "stay_signed_in"
    if any(k in s for k in ["verification code", "approve sign in", "authenticator", "security code", "two-step"]):
        return "mfa"
    if any(k in s for k in ["microsoft dynamics 365", "main.aspx", "make.powerapps.com"]):
        return "app"
    return "other"


async def _fill_username_and_submit(session: ClientSession, tool_names: set[str], username: str) -> str:
    if not username or "browser_evaluate" not in tool_names:
        return "username-skip"
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": f"""
() => {{
  const setValue = (el, value) => {{
    el.focus();
    el.value = value;
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const userSelectors = ['input[type="email"]','input[name="loginfmt"]','input[id="i0116"]','input[autocomplete="username"]','input[type="text"]'];
  const field = userSelectors.map(s => document.querySelector(s)).find(Boolean);
  if (!field) return {{ ok:false, reason:'no-username-field' }};
  setValue(field, {json.dumps(username)});

  const candidates = Array.from(document.querySelectorAll('button,input[type="submit"],input[type="button"],div[role="button"]'));
  const target = candidates.find(el => ['next','sign in','continue'].some(k => ((el.innerText || el.value || '').trim().toLowerCase().includes(k))))
    || document.querySelector('#idSIButton9')
    || document.querySelector('button[type="submit"],input[type="submit"]');
  if (target) {{
    target.click();
    return {{ ok:true, clicked:true }};
  }}
  return {{ ok:true, clicked:false }};
}}
""",
        },
    )
    if "browser_press_key" in tool_names:
        await session.call_tool("browser_press_key", {"key": "Enter"})
    return _extract_text(result)


async def _fill_password_and_submit(session: ClientSession, tool_names: set[str], password: str) -> str:
    if not password or "browser_evaluate" not in tool_names:
        return "password-skip"
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": f"""
() => {{
  const setValue = (el, value) => {{
    el.focus();
    el.value = value;
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const passSelectors = ['input[type="password"]','input[name="passwd"]','input[id="i0118"]','input[autocomplete="current-password"]'];
  const field = passSelectors.map(s => document.querySelector(s)).find(Boolean);
  if (!field) return {{ ok:false, reason:'no-password-field' }};
  setValue(field, {json.dumps(password)});

  const candidates = Array.from(document.querySelectorAll('button,input[type="submit"],input[type="button"],div[role="button"]'));
  const target = candidates.find(el => ['sign in','next','continue'].some(k => ((el.innerText || el.value || '').trim().toLowerCase().includes(k))))
    || document.querySelector('#idSIButton9')
    || document.querySelector('button[type="submit"],input[type="submit"]');
  if (target) {{
    target.click();
    return {{ ok:true, clicked:true }};
  }}
  return {{ ok:true, clicked:false }};
}}
""",
        },
    )
    if "browser_press_key" in tool_names:
        await session.call_tool("browser_press_key", {"key": "Enter"})
    return _extract_text(result)


async def _handle_pick_account(session: ClientSession, tool_names: set[str], username: str) -> str:
    if "browser_evaluate" not in tool_names:
        return "pick-account-skip"
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": f"""
() => {{
  const lowerUser = {json.dumps(username.lower() if username else "")};
  const buttons = Array.from(document.querySelectorAll('button,[role="button"]'));
  let target = null;
  if (lowerUser) {{
    target = buttons.find(el => ((el.innerText || '').toLowerCase().includes(lowerUser)));
  }}
  if (!target) {{
    target = buttons.find(el => ((el.innerText || '').toLowerCase().includes('work or school account')))
      || buttons.find(el => ((el.innerText || '').trim().length > 0));
  }}
  if (target) {{
    target.click();
    return {{ clicked:true, text:(target.innerText || '').trim().slice(0,120) }};
  }}
  return {{ clicked:false }};
}}
""",
        },
    )
    return _extract_text(result)


async def _handle_stay_signed_in(session: ClientSession, tool_names: set[str]) -> str:
    if "browser_evaluate" not in tool_names:
        return "stay-signed-in-skip"
    result = await session.call_tool(
        "browser_evaluate",
        {
            "function": """
() => {
  const checkbox = document.querySelector('#KmsiCheckboxField,input[type="checkbox"]');
  if (checkbox && !checkbox.checked) {
    checkbox.click();
  }
  const byId = document.querySelector('#idSIButton9');
  if (byId) {
    byId.click();
    return { clicked: true, text: 'idSIButton9' };
  }
  const buttons = Array.from(document.querySelectorAll('button,input[type="submit"],input[type="button"],div[role="button"]'));
  const yes = buttons.find(el => ['yes','continue','ok','sign in'].some(k => ((el.innerText || el.value || '').trim().toLowerCase().includes(k))));
  if (yes) {
    yes.click();
    return { clicked: true, text: (yes.innerText || yes.value || '').trim() };
  }
  return { clicked: false };
}
""",
        },
    )
    return _extract_text(result)


async def _run_auth_bridge(
    session: ClientSession,
    tool_names: set[str],
    report_dir: Path,
    scenario_slug: str,
    username: str,
    password: str,
    requires_mfa: bool,
    mfa_code_file: Path,
    mfa_timeout_seconds: int,
    page_settle_seconds: int,
    progress_cb: Callable[[str, str, str | None], None] | None,
    target_url: str,
) -> None:
    if not username and not password:
        return

    _emit(progress_cb, "running", "Auth bridge started (deterministic login progression).")
    _append_planner_trace(
        report_dir,
        {"kind": "auth_bridge_start", "scenario": scenario_slug, "target_url": target_url},
    )
    for step in range(1, 31):
        snapshot = await _get_compact_state(session, tool_names)
        stage = _stage_from_snapshot(snapshot)
        _emit(progress_cb, "running", f"Auth bridge stage: {stage}.")
        _append_planner_trace(
            report_dir,
            {
                "kind": "auth_bridge_stage",
                "step": step,
                "stage": stage,
                "snapshot_preview": snapshot[:1200],
            },
        )

        if stage == "username":
            out = await _fill_username_and_submit(session, tool_names, username)
            _emit(progress_cb, "running", f"Auth bridge username action: {out[:220]}")
        elif stage == "password":
            out = await _fill_password_and_submit(session, tool_names, password)
            _emit(progress_cb, "running", f"Auth bridge password action: {out[:220]}")
        elif stage == "pick_account":
            out = await _handle_pick_account(session, tool_names, username)
            _emit(progress_cb, "running", f"Auth bridge pick-account action: {out[:220]}")
        elif stage == "stay_signed_in":
            out = await _handle_stay_signed_in(session, tool_names)
            _emit(progress_cb, "running", f"Auth bridge stay-signed-in action: {out[:220]}")
        elif stage == "mfa":
            if not requires_mfa:
                _emit(progress_cb, "running", "MFA detected but scenario MFA flag is off; pausing bridge.")
                return
            mfa_shot = await _take_screenshot(
                session,
                tool_names,
                report_dir,
                scenario_slug,
                "bridge-mfa",
                progress_cb=progress_cb,
            )
            if mfa_shot:
                _emit(progress_cb, "waiting_mfa", "Auth bridge captured MFA screenshot.", mfa_shot)
            ready = await _wait_for_mfa_code(
                session=session,
                tool_names=tool_names,
                mfa_code_file=mfa_code_file,
                timeout_seconds=mfa_timeout_seconds,
                report_dir=report_dir,
                scenario_slug=scenario_slug,
                progress_cb=progress_cb,
            )
            if not ready:
                return
        elif stage == "app":
            _emit(progress_cb, "running", "Auth bridge detected authenticated app page; handing over to LLM.")
            if target_url:
                await session.call_tool("browser_navigate", {"url": target_url})
                _emit(progress_cb, "running", f"Auth bridge navigated to target URL: {target_url}")
                if page_settle_seconds > 0:
                    await asyncio.sleep(page_settle_seconds)
            return
        else:
            if "browser_press_key" in tool_names:
                await session.call_tool("browser_press_key", {"key": "Enter"})

        bridge_shot = await _take_screenshot(
            session,
            tool_names,
            report_dir,
            scenario_slug,
            f"bridge-{step}",
            progress_cb=progress_cb,
        )
        if bridge_shot:
            _emit(progress_cb, "running", f"Auth bridge screenshot {step}.", bridge_shot)
        if page_settle_seconds > 0:
            await asyncio.sleep(page_settle_seconds)


async def run_mcp_check(
    mcp_url: str,
    url: str,
    expected_text: str,
    timeout_seconds: int,
    report_dir: Path,
    scenario_slug: str,
    requires_mfa: bool = False,
    mfa_code_file: Path | None = None,
    mfa_timeout_seconds: int = 180,
    username: str = "",
    password: str = "",
    page_settle_seconds: int = 5,
    test_goal: str = "",
    agent_max_steps: int = 15,
    manual_login_handoff: bool = True,
    manual_login_timeout_seconds: int = 900,
    progress_cb: Callable[[str, str, str | None], None] | None = None,
) -> MCPCheckResult:
    start = datetime.now(timezone.utc)
    last_error: Exception | None = None

    planner_client, planner_model = _build_llm_client()

    context = PlannerContext(
        goal=test_goal or f"Open {url} and complete the test flow.",
        expected_text=expected_text,
        username=username,
        password=password,
        mfa_hint=(
            "MFA may be required. If challenge appears, request await_human_code action."
            if requires_mfa
            else "No MFA expected."
        ),
        objectives=_extract_objectives(test_goal or f"Open {url} and complete the test flow."),
    )

    for attempt in range(1, 4):
        try:
            async with asyncio.timeout(timeout_seconds):
                sse_url = _to_sse_url(mcp_url)
                async with sse_client(sse_url) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        try:
                            _emit(progress_cb, "running", f"Connected to MCP SSE transport on attempt {attempt}.")
                            await session.initialize()
                            tools_response = await session.list_tools()
                            tool_names = {tool.name for tool in tools_response.tools}

                            await session.call_tool("browser_navigate", {"url": url})
                            _emit(progress_cb, "running", f"Navigated to {url}.")
                            if page_settle_seconds > 0:
                                _emit(progress_cb, "running", f"Waiting {page_settle_seconds}s for initial page settle.")
                                await asyncio.sleep(page_settle_seconds)

                            initial_shot = await _take_screenshot(
                                session,
                                tool_names,
                                report_dir,
                                scenario_slug,
                                "after-navigate",
                                progress_cb=progress_cb,
                            )
                            if initial_shot:
                                _emit(progress_cb, "running", "Captured initial screenshot.", initial_shot)

                            if manual_login_handoff:
                                _emit(
                                    progress_cb,
                                    "running",
                                    "Manual login handoff enabled. Please complete login in VNC; automation starts after Dataverse main.aspx is fully loaded.",
                                )
                                handoff_ok, handoff_url = await _wait_for_manual_login_handoff(
                                    session=session,
                                    tool_names=tool_names,
                                    target_url=url,
                                    timeout_seconds=manual_login_timeout_seconds,
                                    report_dir=report_dir,
                                    scenario_slug=scenario_slug,
                                    progress_cb=progress_cb,
                                )
                                if not handoff_ok:
                                    end = datetime.now(timezone.utc)
                                    duration = (end - start).total_seconds()
                                    return MCPCheckResult(
                                        passed=False,
                                        details=f"Manual login handoff timed out after {manual_login_timeout_seconds}s.",
                                        snapshot_excerpt="(No snapshot text captured)",
                                        duration_seconds=duration,
                                        tool_count=len(tool_names),
                                    )
                                if handoff_url:
                                    history = [f"handoff:{handoff_url}"]
                                else:
                                    history = [f"handoff:{url}"]
                            else:
                                await _run_auth_bridge(
                                    session=session,
                                    tool_names=tool_names,
                                    report_dir=report_dir,
                                    scenario_slug=scenario_slug,
                                    username=username,
                                    password=password,
                                    requires_mfa=requires_mfa,
                                    mfa_code_file=mfa_code_file or Path("/app/scenarios/mfa_code.txt"),
                                    mfa_timeout_seconds=mfa_timeout_seconds,
                                    page_settle_seconds=page_settle_seconds,
                                    progress_cb=progress_cb,
                                    target_url=url,
                                )
                                history = [f"navigate:{url}"]
                            post_auth_objectives = _extract_post_auth_objectives(context.goal)
                            if post_auth_objectives:
                                context.objectives = post_auth_objectives
                                context.goal = "Post-auth objectives:\n" + "\n".join(f"- {o}" for o in post_auth_objectives)

                            history = list(history)
                            snapshot_text = ""
                            passed = False
                            details = ""
                            expected_seen = False
                            last_state_key = ""
                            stuck_count = 0
                            last_tool_name = ""
                            forced_transition_uses = 0
                            objective_status = [False for _ in context.objectives]
                            passive_action_count = 0
                            last_action_signature = ""
                            repeated_action_count = 0

                            for step in range(1, max(1, agent_max_steps) + 1):
                                snapshot_text = await _get_compact_state(session, tool_names)
                                target_page_loaded = _is_target_url_loaded_from_snapshot(snapshot_text, url)
                                if not target_page_loaded:
                                    target_page_loaded = await _is_target_url_loaded(session, tool_names, url)
                                state_key = snapshot_text[:1200]
                                if state_key == last_state_key:
                                    stuck_count += 1
                                else:
                                    stuck_count = 0
                                    forced_transition_uses = 0
                                last_state_key = state_key

                                loop_shot = await _take_screenshot(
                                    session,
                                    tool_names,
                                    report_dir,
                                    scenario_slug,
                                    f"loop-{step}",
                                    progress_cb=progress_cb,
                                )
                                if loop_shot:
                                    _emit(progress_cb, "running", f"Captured loop screenshot {step}.", loop_shot)

                                if expected_text and expected_text.lower() in snapshot_text.lower():
                                    if not expected_seen:
                                        expected_seen = True
                                        _emit(progress_cb, "running", f"Expected text '{expected_text}' found. Continuing prompt execution.")
                                objective_status = _reconcile_objective_status(
                                    context.objectives,
                                    objective_status,
                                    snapshot_text,
                                )
                                next_objective = _next_pending_objective(context.objectives, objective_status)
                                if target_page_loaded:
                                    auto_marked = False
                                    for idx, obj in enumerate(context.objectives):
                                        if idx < len(objective_status) and not objective_status[idx] and _is_page_load_objective(obj):
                                            objective_status[idx] = True
                                            auto_marked = True
                                    if auto_marked:
                                        history.append("auto_complete_page_loaded_objective")
                                        _emit(
                                            progress_cb,
                                            "running",
                                            "Marked page-load objective complete because Dataverse URL is fully loaded.",
                                        )
                                        next_objective = _next_pending_objective(context.objectives, objective_status)

                                forced_action: dict[str, Any] | None = None
                                if (
                                    stuck_count >= 1
                                    and forced_transition_uses < 3
                                    and _looks_like_auth_step(snapshot_text)
                                    and last_tool_name in {"browser_type", "browser_fill_form", "browser_click"}
                                ):
                                    if username or password:
                                        fallback_result = await _fallback_auth_progress(
                                            session=session,
                                            tool_names=tool_names,
                                            username=username,
                                            password=password,
                                        )
                                        history.append(f"auth_fallback:{fallback_result[:180]}")
                                        _emit(progress_cb, "running", f"Auth fallback progress: {fallback_result[:220]}")
                                    if "browser_evaluate" in tool_names:
                                        forced_action = {
                                            "action": "tool",
                                            "tool_name": "browser_evaluate",
                                            "arguments": {
                                                "function": """
() => {
  const candidates = Array.from(document.querySelectorAll('button,input[type="submit"],input[type="button"],div[role="button"]'));
  const preferred = ['next', 'sign in', 'continue', 'yes', 'submit'];
  for (const p of preferred) {
    const hit = candidates.find(el => ((el.innerText || el.value || '').trim().toLowerCase().includes(p)));
    if (hit) {
      hit.click();
      return {clicked: true, target: p, text: (hit.innerText || hit.value || '').trim()};
    }
  }
  const submit = document.querySelector('button[type="submit"],input[type="submit"]');
  if (submit) {
    submit.click();
    return {clicked: true, target: 'submit'};
  }
  return {clicked: false};
}
""",
                                            },
                                            "message": "Auth step appears stalled after input; forcing transition by clicking a submit-like control.",
                                        }
                                    elif "browser_press_key" in tool_names:
                                        forced_action = {
                                            "action": "tool",
                                            "tool_name": "browser_press_key",
                                            "arguments": {"key": "Enter"},
                                            "message": "Auth step appears stalled after input; forcing transition with Enter.",
                                        }
                                    forced_transition_uses += 1

                                if forced_action:
                                    action = forced_action
                                else:
                                    action = _plan_next_action(
                                        planner_client=planner_client,
                                        model=planner_model,
                                        tools=tool_names,
                                        context=context,
                                        snapshot_text=snapshot_text,
                                        history=history,
                                        step=step,
                                        max_steps=agent_max_steps,
                                        stuck_count=stuck_count,
                                        objective_status=objective_status,
                                        next_objective=next_objective,
                                        target_page_loaded=target_page_loaded,
                                        report_dir=report_dir,
                                    )

                                action_type = str(action.get("action", "")).strip().lower()
                                message = str(action.get("message", "")).strip()
                                if message:
                                    _emit(progress_cb, "running", f"Planner: {message}")

                                if action_type == "finish":
                                    planned_success = bool(action.get("success", False))
                                    objective_status = _reconcile_objective_status(
                                        context.objectives,
                                        objective_status,
                                        snapshot_text,
                                    )
                                    all_objectives_done = all(objective_status) if objective_status else True
                                    if not all_objectives_done:
                                        pending = [context.objectives[i] for i, done in enumerate(objective_status) if not done][:4]
                                        history.append("finish_blocked_pending_objectives")
                                        _emit(
                                            progress_cb,
                                            "running",
                                            "Finish blocked: pending objectives -> " + " | ".join(pending),
                                        )
                                        continue
                                    passed = planned_success
                                    details = message or ("Planner marked scenario complete." if passed else "Planner marked scenario failed.")
                                    break

                                if action_type == "await_human_code":
                                    if not requires_mfa:
                                        history.append("await_human_code_requested_but_mfa_not_enabled")
                                        continue

                                    mfa_visible = await _is_mfa_ui_visible(session, tool_names)
                                    if not mfa_visible:
                                        history.append("await_human_code_requested_but_mfa_not_visible")
                                        _emit(
                                            progress_cb,
                                            "running",
                                            "Planner requested MFA wait, but no MFA UI detected yet. Continuing autonomous steps.",
                                        )
                                        continue

                                    mfa_shot = await _take_screenshot(
                                        session,
                                        tool_names,
                                        report_dir,
                                        scenario_slug,
                                        "mfa",
                                        progress_cb=progress_cb,
                                    )
                                    if mfa_shot:
                                        _emit(progress_cb, "waiting_mfa", "Captured MFA checkpoint screenshot.", mfa_shot)

                                    ready = await _wait_for_mfa_code(
                                        session=session,
                                        tool_names=tool_names,
                                        mfa_code_file=mfa_code_file or Path("/app/scenarios/mfa_code.txt"),
                                        timeout_seconds=mfa_timeout_seconds,
                                        report_dir=report_dir,
                                        scenario_slug=scenario_slug,
                                        progress_cb=progress_cb,
                                    )
                                    history.append("await_human_code")
                                    if not ready:
                                        passed = False
                                        details = "MFA required but code was not submitted successfully."
                                        break
                                    continue

                                if action_type == "tool":
                                    proposed_tool_name = str(action.get("tool_name", "")).strip()
                                    proposed_arguments = action.get("arguments", {}) or {}
                                    if proposed_tool_name == "browser_wait_for" and target_page_loaded:
                                        wait_text = str(proposed_arguments.get("text", "")).strip().lower()
                                        expected_low = (expected_text or "").strip().lower()
                                        if (
                                            not wait_text
                                            or "microsoft dynamics" in wait_text
                                            or "dynamics 365" in wait_text
                                            or (expected_low and expected_low in wait_text)
                                        ):
                                            history.append("skip_brittle_wait_for_text_target_page_already_loaded")
                                            _emit(
                                                progress_cb,
                                                "running",
                                                "Skipping text-based wait because target Dataverse URL is already fully loaded.",
                                            )
                                            if next_objective and _is_page_load_objective(next_objective):
                                                try:
                                                    idx = context.objectives.index(next_objective)
                                                    objective_status[idx] = True
                                                    history.append("auto_complete_skipped_wait_objective")
                                                    _emit(progress_cb, "running", "Advanced to next objective after skipping redundant wait.")
                                                except ValueError:
                                                    pass
                                            continue
                                    action_signature = f"{proposed_tool_name}:{json.dumps(action.get('arguments', {}), sort_keys=True, default=str)}"
                                    if action_signature == last_action_signature:
                                        repeated_action_count += 1
                                    else:
                                        repeated_action_count = 0
                                        last_action_signature = action_signature
                                    if proposed_tool_name in {"browser_wait_for", "browser_take_screenshot"}:
                                        passive_action_count += 1
                                    else:
                                        passive_action_count = 0

                                    if next_objective and passive_action_count >= 3:
                                        progress = await _attempt_objective_progress(
                                            session=session,
                                            tool_names=tool_names,
                                            objective=next_objective,
                                        )
                                        history.append(f"objective_progress:{progress[:180]}")
                                        _emit(progress_cb, "running", f"Objective progress nudge: {progress[:220]}")
                                        passive_action_count = 0
                                        continue

                                    if next_objective and repeated_action_count >= 2:
                                        progress = await _attempt_objective_progress(
                                            session=session,
                                            tool_names=tool_names,
                                            objective=next_objective,
                                        )
                                        history.append(f"objective_progress_repeat_break:{progress[:180]}")
                                        _emit(progress_cb, "running", f"Repeated-action breaker: {progress[:220]}")
                                        repeated_action_count = 0
                                        continue

                                    if (
                                        stuck_count >= 2
                                        and proposed_tool_name in {"browser_type", "browser_fill_form"}
                                        and last_tool_name in {"browser_type", "browser_fill_form"}
                                    ):
                                        history.append(f"blocked_repeat_input:{proposed_tool_name}")
                                        _emit(
                                            progress_cb,
                                            "running",
                                            "Blocked repeated input action on unchanged screen; requesting transition action.",
                                        )
                                        continue

                                    result_text, error = await _execute_tool_action(
                                        session=session,
                                        tool_names=tool_names,
                                        action=action,
                                        report_dir=report_dir,
                                        scenario_slug=scenario_slug,
                                        step=step,
                                        progress_cb=progress_cb,
                                    )
                                    if error:
                                        history.append(f"error:{error}")
                                        _emit(progress_cb, "running", error)
                                    else:
                                        last_tool_name = proposed_tool_name
                                        brief = result_text[:240].replace("\n", " ")
                                        history.append(f"tool:{action.get('tool_name')} -> {brief}")
                                        # Use action/result evidence (not full snapshot) to avoid
                                        # prematurely completing future objectives just because labels
                                        # like "Contacts" or "New" are visible somewhere on the page.
                                        objective_evidence = f"{proposed_tool_name} {brief}"
                                        objective_status = _update_objective_status(
                                            context.objectives,
                                            objective_status,
                                            objective_evidence,
                                        )
                                        if proposed_tool_name == "browser_take_screenshot":
                                            # Prevent screenshot-only loops: a successful screenshot should
                                            # complete the next pending screenshot objective immediately.
                                            marked_screenshot_obj = False
                                            for idx, obj in enumerate(context.objectives):
                                                if idx < len(objective_status) and not objective_status[idx] and _is_screenshot_objective(obj):
                                                    objective_status[idx] = True
                                                    marked_screenshot_obj = True
                                                    break
                                            if marked_screenshot_obj:
                                                history.append("auto_complete_screenshot_objective")
                                                _emit(
                                                    progress_cb,
                                                    "running",
                                                    "Marked screenshot objective complete after successful screenshot.",
                                                )
                                        step_shot = await _take_screenshot(
                                            session,
                                            tool_names,
                                            report_dir,
                                            scenario_slug,
                                            f"step-{step}",
                                            progress_cb=progress_cb,
                                        )
                                        if step_shot:
                                            _emit(progress_cb, "running", f"Captured step screenshot {step}.", step_shot)
                                    if page_settle_seconds > 0:
                                        await asyncio.sleep(page_settle_seconds)
                                    continue

                                history.append(f"invalid_action:{action}")
                                _emit(progress_cb, "running", "Planner returned invalid action, continuing.")

                            else:
                                passed = False
                                details = f"Agent exceeded max steps ({agent_max_steps}) without finishing."

                            if not details:
                                details = "Validation completed."

                            end = datetime.now(timezone.utc)
                            duration = (end - start).total_seconds()
                            excerpt = snapshot_text[:500].replace("\n", " ") if snapshot_text else "(No snapshot text captured)"

                            return MCPCheckResult(
                                passed=passed,
                                details=details,
                                snapshot_excerpt=excerpt,
                                duration_seconds=duration,
                                tool_count=len(tool_names),
                            )
                        except Exception as inner_exc:
                            _emit(progress_cb, "failed", f"MCP inner flow error: {inner_exc}")
                            end = datetime.now(timezone.utc)
                            duration = (end - start).total_seconds()
                            return MCPCheckResult(
                                passed=False,
                                details=f"MCP inner flow error: {inner_exc}",
                                snapshot_excerpt="(No snapshot text captured)",
                                duration_seconds=duration,
                                tool_count=0,
                            )

        except Exception as exc:
            last_error = exc
            if attempt < 3:
                _emit(progress_cb, "running", f"MCP connect attempt {attempt} failed. Retrying in 2 seconds.")
                await asyncio.sleep(2)
                continue
            raise RuntimeError(f"Unable to execute MCP flow at {mcp_url}: {last_error}") from last_error

    end = datetime.now(timezone.utc)
    duration = (end - start).total_seconds()
    return MCPCheckResult(
        passed=False,
        details=f"MCP flow failed: {last_error}",
        snapshot_excerpt="(No snapshot text captured)",
        duration_seconds=duration,
        tool_count=0,
    )
