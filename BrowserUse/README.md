# Autonomous Playwright MCP Docker Automation

This project runs website automation checks in Docker using:
- `mcr.microsoft.com/playwright/mcp` for browser control
- an LLM-driven MCP agent loop (snapshot -> decide -> tool action)
- optional `browser-use` secondary step (disabled by default)
- JSON + HTML reporting under `reports/`

## How it works

For each scenario in `scenarios/default.json`:
1. MCP agent reads your prompt goal and current snapshot
2. Agent decides next action (`tool`, `await_human_code`, `finish`) and executes via Playwright MCP
3. Agent repeats until completion or max steps
4. `browser-use` runs only if `RUN_BROWSER_USE=true`
3. Results are written to:
   - `reports/report.json`
   - `reports/report.html`
   - `reports/live/<scenario-name>.html` (auto-refresh progress page per test)

## Prerequisites

- Docker Desktop running
- LLM credentials for browser-use execution:
  - Azure AI Foundry / Azure OpenAI (recommended for your setup):
    - `AZURE_OPENAI_ENDPOINT`
    - `AZURE_OPENAI_API_KEY`
    - `AZURE_OPENAI_DEPLOYMENT_NAME`
    - optional: `AZURE_OPENAI_API_VERSION` (default `2024-12-01-preview`)
  - or standard OpenAI:
    - `OPENAI_API_KEY`

Default is autonomous MCP mode with optional browser-use disabled (`RUN_BROWSER_USE=false`).

## Local run steps (Windows PowerShell)

1. Open Docker Desktop and wait until it shows `Engine running`.
2. In this repo, edit your prompt in `scenarios/prompt.txt`.
3. Optionally edit test targets/assertions in `scenarios/default.json`.
4. Create your env file from template:
   ```powershell
   Copy-Item .env.example .env
   ```
5. Edit `.env` and set your Azure AI Foundry values:
   ```dotenv
   AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
   AZURE_OPENAI_API_KEY=<your_azure_key>
   AZURE_OPENAI_DEPLOYMENT_NAME=<your_model_deployment_name>
   AZURE_OPENAI_API_VERSION=2024-12-01-preview
   ```
6. Start the run:
   ```powershell
   docker compose up --build --abort-on-container-exit
   ```
7. Open report:
   - `reports/report.html`
   - `reports/report.json`
   - `reports/live/*.html` for live per-test progress

## Browser-use toggle

- Stable default: `RUN_BROWSER_USE=false` (MCP-only)
- Enable browser-use:
  - Set `RUN_BROWSER_USE=true` in `.env`
  - Provide Azure/OpenAI credentials

## Browser engine toggle

- Set `MCP_BROWSER` in `.env`:
  - `chromium` (default)
  - `msedge` (to test Edge behavior)
  - `chrome` / `firefox` / `webkit` (if supported in your environment)
- Set `MCP_HEADLESS=false` to see the browser in noVNC (`true` hides the browser window).

## MCP agent controls

- `TEST_TIMEOUT_SECONDS`: total timeout for one scenario run (default `300`)
- `PAGE_SETTLE_SECONDS`: fixed wait between key actions (default `5`)
- `MCP_AGENT_MAX_STEPS`: maximum decision loop steps before fail-safe stop (default `30`)

## Prompt file format

`scenarios/prompt.txt` is plain text. Example:

```text
Open https://example.com and verify the main heading says "Example Domain".
Then explain what the page is for in 2 concise bullet points and include a confidence level.
```

## Scenario file format

```json
{
  "scenarios": [
    {
      "name": "Example Domain smoke check",
      "url": "https://example.com",
      "expected_text": "Example Domain"
    }
  ]
}
```

You can also override prompt per scenario:

```json
{
  "name": "Scenario with custom prompt",
  "url": "https://example.com",
  "expected_text": "Example Domain",
  "prompt": "Open https://example.com, check heading, and summarize key points."
}
```

## MFA and Dataverse logins

For MFA-protected environments, use human-in-the-loop mode:
- Add this in a scenario:
```json
{
  "name": "Dataverse login flow",
  "url": "https://make.powerapps.com",
  "expected_text": "Power Apps",
  "requires_mfa": true,
  "mfa_timeout_seconds": 240
}
```
- While the live report status is `waiting_mfa`, enter your OTP code in `scenarios/mfa_code.txt`.
- For push-notification MFA (no numeric code), you can also put `approved` in `scenarios/mfa_code.txt` to continue.
- The runner submits that code into the focused MFA field and continues.
- To get a useful MFA screenshot, set credentials in `.env` so MCP submits login first:
  - `TEST_USERNAME=<your-user>`
  - `TEST_PASSWORD=<your-password>`
  - Then screenshots are captured after credential submission and repeatedly during MFA wait.

## Important note on headed mode

The MCP browser runs inside Docker. Even in headed mode, you typically do not get an interactive desktop window on your host.  
Use:
- `reports/live/*.html` for step-by-step status
- `reports/screenshots/*.png` for page snapshots (including MFA checkpoints)

## Live VNC View

This setup now includes noVNC so you can watch the browser session live.

1. Start stack:
```powershell
docker compose up --build --abort-on-container-exit
```
2. Open browser view:
- `http://localhost:6080/vnc.html?autoconnect=1&resize=remote`

Notes:
- MCP API stays on `http://localhost:8931/mcp`.
- Raw VNC is also exposed on port `5900` if you use a VNC client.
