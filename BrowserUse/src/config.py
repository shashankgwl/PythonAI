import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    mcp_url: str = os.getenv("MCP_URL", "http://playwright-mcp:8931/mcp")
    scenario_file: Path = Path(os.getenv("SCENARIO_FILE", "/app/scenarios/default.json"))
    prompt_file: Path = Path(os.getenv("PROMPT_FILE", "/app/scenarios/prompt.txt"))
    mfa_code_file: Path = Path(os.getenv("MFA_CODE_FILE", "/app/scenarios/mfa_code.txt"))
    mfa_timeout_seconds: int = int(os.getenv("MFA_TIMEOUT_SECONDS", "180"))
    report_dir: Path = Path(os.getenv("REPORT_DIR", "/app/reports"))
    template_path: Path = Path(os.getenv("REPORT_TEMPLATE", "/app/templates/report.html.j2"))
    timeout_seconds: int = int(os.getenv("TEST_TIMEOUT_SECONDS", "300"))
    page_settle_seconds: int = int(os.getenv("PAGE_SETTLE_SECONDS", "5"))
    agent_max_steps: int = int(os.getenv("MCP_AGENT_MAX_STEPS", "60"))
    run_browser_use: bool = os.getenv("RUN_BROWSER_USE", "false").lower() in {"1", "true", "yes", "on"}
    test_username: str = os.getenv("TEST_USERNAME", os.getenv("DATAVERSE_USERNAME", ""))
    test_password: str = os.getenv("TEST_PASSWORD", os.getenv("DATAVERSE_PASSWORD", ""))
    manual_login_handoff: bool = os.getenv("MANUAL_LOGIN_HANDOFF", "true").lower() in {"1", "true", "yes", "on"}
    manual_login_timeout_seconds: int = int(os.getenv("MANUAL_LOGIN_TIMEOUT_SECONDS", "900"))


def load_scenarios(path: Path) -> list[dict]:
    if not path.exists():
        return [
            {
                "name": "Example Domain contains expected text",
                "url": "https://example.com",
                "expected_text": "Example Domain",
            }
        ]

    content = path.read_text(encoding="utf-8")
    data = json.loads(content)

    if isinstance(data, dict):
        scenarios = data.get("scenarios", [])
    elif isinstance(data, list):
        scenarios = data
    else:
        raise ValueError("Scenario file must be a JSON object or array.")

    if not scenarios:
        raise ValueError("No scenarios found in scenario file.")

    return scenarios


def load_prompt(path: Path) -> str | None:
    if not path.exists():
        return None

    prompt = path.read_text(encoding="utf-8").strip()
    return prompt or None
