# Prompt HTTP Server

Browser-friendly HTTP JSON server for SharePoint prompts.

It returns the same prompt record shape as the MCP server:

```json
[
  {
    "item_id": "1",
    "web_url": "https://...",
    "prompt_id": "11",
    "title": "Login Prompt",
    "prompt_text": "..."
  }
]
```

## Endpoints

Use either endpoint:

```text
http://localhost:8080/?promptID=11
http://localhost:8080/prompt?promptID=11
http://localhost:8080/?promptTitle=Login%20Prompt
http://localhost:8080/prompt?promptTitle=Login%20Prompt
```

Pass exactly one query parameter:

- `promptID`
- `promptTitle`

The response is printed directly as JSON in the browser.

## Configure

Create `.env`:

```powershell
Copy-Item .env.example .env
```

Fill in the Azure app credentials:

```env
AZURE_TENANT_ID=<tenant-id>
AZURE_CLIENT_ID=<app-client-id>
AZURE_CLIENT_SECRET=<client-secret-value>
```

The SharePoint defaults are:

```env
SHAREPOINT_SITE_URL=https://1xqy71.sharepoint.com/sites/ShankySP
SHAREPOINT_LIST_NAME=Prompt List
PROMPT_ID_FIELD=PromptId
TITLE_FIELD=Title
PROMPT_TEXT_FIELD=PromptText
```

## Run With Docker

```powershell
cd prompt-http-server
docker compose up --build
```

Then open:

```text
http://localhost:8080/?promptID=11
```
