from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path


@dataclass
class LiveProgress:
    report_dir: Path
    scenario_name: str
    slug: str
    status: str = "pending"
    events: list[dict[str, str]] = field(default_factory=list)
    screenshot_path: str = ""
    screenshots: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.live_dir = self.report_dir / "live"
        self.live_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.live_dir / f"{self.slug}.html"
        self.add_event("pending", "Scenario initialized.")

    def add_event(self, status: str, message: str, screenshot_path: str | None = None) -> None:
        self.status = status
        if screenshot_path:
            self.screenshot_path = screenshot_path
            if screenshot_path not in self.screenshots:
                self.screenshots.append(screenshot_path)
        self.events.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "message": message,
            }
        )
        self._write()

    def _write(self) -> None:
        color = {
            "pending": "#5b6b80",
            "running": "#0e7490",
            "waiting_mfa": "#b45309",
            "passed": "#166534",
            "failed": "#b91c1c",
        }.get(self.status, "#5b6b80")

        rows = "".join(
            (
                "<tr>"
                f"<td>{escape(event['time'])}</td>"
                f"<td>{escape(event['status'])}</td>"
                f"<td>{escape(event['message'])}</td>"
                "</tr>"
            )
            for event in reversed(self.events)
        )

        screenshot_items = ""
        for path in reversed(self.screenshots):
            screenshot_items += (
                "<div class='shot-item'>"
                f"<p class='shot-path'>{escape(path)}</p>"
                f"<img src='../{escape(path)}' alt='screenshot' class='shot-img'/>"
                "</div>"
            )
        if not screenshot_items:
            screenshot_items = "<p class='muted'>No screenshots yet.</p>"

        html = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta http-equiv='refresh' content='2'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Live Test Progress - {escape(self.scenario_name)}</title>
  <style>
    body {{ font-family: Segoe UI, Tahoma, sans-serif; background: #f4f7fb; margin: 0; color: #1f2937; }}
    .wrap {{ max-width: 1400px; margin: 24px auto; padding: 0 16px; }}
    .card {{ background: white; border: 1px solid #dbe3ee; border-radius: 12px; padding: 16px; margin-bottom: 12px; }}
    .status {{ display: inline-block; padding: 4px 10px; border-radius: 999px; color: white; background: {color}; font-size: 12px; letter-spacing: 0.05em; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #eef2f7; padding: 8px; text-align: left; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 12px; align-items: start; }}
    .events-card {{ max-height: 75vh; overflow: auto; }}
    .shots-card {{ max-height: 75vh; overflow: auto; position: sticky; top: 12px; }}
    .shot-item {{ margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #eef2f7; }}
    .shot-path {{ margin: 0 0 8px 0; font-size: 12px; color: #5b6b80; word-break: break-all; }}
    .shot-img {{ width: 100%; border: 1px solid #dbe3ee; border-radius: 8px; display: block; }}
    .muted {{ color: #5b6b80; }}
    @media (max-width: 1000px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .events-card, .shots-card {{ max-height: none; position: static; }}
    }}
  </style>
</head>
<body>
  <div class='wrap'>
    <div class='card'>
      <h2>{escape(self.scenario_name)}</h2>
      <span class='status'>{escape(self.status)}</span>
      <p>Auto-refreshes every 2 seconds.</p>
      <p>If MFA is required, put the code in <code>scenarios/mfa_code.txt</code> while this status is <code>waiting_mfa</code>.</p>
    </div>
    <div class='grid'>
      <div class='card events-card'>
        <h3>Events</h3>
        <table>
          <thead><tr><th>Time (UTC)</th><th>Status</th><th>Message</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      <div class='card shots-card'>
        <h3>Screenshots</h3>
        {screenshot_items}
      </div>
    </div>
  </div>
</body>
</html>"""
        self.file_path.write_text(html, encoding="utf-8")
