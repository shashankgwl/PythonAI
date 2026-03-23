from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Template


def write_reports(results: list[dict[str, Any]], report_dir: Path, template_path: Path) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc).isoformat()
    total = len(results)
    passed = sum(1 for result in results if result.get("overall_status") == "passed")
    failed = total - passed

    summary = {
        "generated_at": generated_at,
        "total": total,
        "passed": passed,
        "failed": failed,
        "success_rate": round((passed / total) * 100, 2) if total else 0,
        "results": results,
    }

    json_path = report_dir / "report.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    template_content = template_path.read_text(encoding="utf-8")
    html = Template(template_content).render(summary=summary)

    html_path = report_dir / "report.html"
    html_path.write_text(html, encoding="utf-8")

    return {"json": json_path, "html": html_path}
