# SharePoint Prompt MCP Server

FastMCP HTTP server that reads prompt records from the SharePoint list:

`https://1xqy71.sharepoint.com/sites/ShankySP/Lists/Prompt%20List`

The MCP SSE endpoint is:

`http://localhost:8077/sse`

## Tools

- `GetPromptsByTitle(title)`: returns prompts whose SharePoint `Title` exactly matches `title`.
- `GetPromptsById(prompt_id)`: returns prompts whose `Prompt Id` exactly matches `prompt_id`.

Each result includes:

- `prompt_id`
- `title`
- `prompt_text`
- `item_id`
- `web_url`

## Azure App Registration

Create an app registration in Microsoft Entra ID:

1. Go to Azure Portal > Microsoft Entra ID > App registrations > New registration.
2. Name it something like `sharepoint-prompt-mcp`.
3. Use `Accounts in this organizational directory only`.
4. Create the app, then copy:
   - Directory tenant ID -> `AZURE_TENANT_ID`
   - Application client ID -> `AZURE_CLIENT_ID`
5. Go to Certificates & secrets > Client secrets > New client secret.
6. Copy the secret **Value** immediately -> `AZURE_CLIENT_SECRET`.

Grant Microsoft Graph application permissions:

1. In the app registration, go to API permissions > Add a permission.
2. Choose Microsoft Graph > Application permissions.
3. Add one of these permission sets:
   - Broad/simple: `Sites.Read.All`
   - Tighter: `Sites.Selected`, then grant this app read access to the specific site with Graph or PnP PowerShell.
4. Click Grant admin consent.

For the simplest first run, use `Sites.Read.All`. Move to `Sites.Selected` later if you need least-privilege production access.

## Configure

Create `sharepoint-prompt-mcp/.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Fill in:

```env
AZURE_TENANT_ID=<your-tenant-id>
AZURE_CLIENT_ID=<your-app-client-id>
AZURE_CLIENT_SECRET=<your-client-secret-value>
SHAREPOINT_SITE_URL=https://1xqy71.sharepoint.com/sites/ShankySP/Lists/Prompt%20List
SHAREPOINT_LIST_NAME=Prompt List
```

SharePoint display names can contain spaces, but Graph returns fields by their internal names. The defaults should match your columns:

```env
PROMPT_ID_FIELD=PromptId
TITLE_FIELD=Title
PROMPT_TEXT_FIELD=PromptText
```

If the list was created with different original column names, confirm the internal names in SharePoint List settings or with Graph and update these values.

## Run Locally With Docker

```powershell
cd sharepoint-prompt-mcp
docker compose up --build
```

The MCP SSE endpoint will be available at:

```text
http://localhost:8077/sse
```

## Verify The MCP Tool

Use the MCP Python client rather than a raw REST payload:

```powershell
cd sharepoint-prompt-mcp
python verify_mcp.py 11
```

This connects to the SSE endpoint, initializes the MCP session, lists tools, then calls `GetPromptsById` with prompt id `11`.

## Build Without Compose

```powershell
cd sharepoint-prompt-mcp
docker build -t sharepoint-prompt-mcp .
docker run --rm -p 8077:8077 --env-file .env sharepoint-prompt-mcp
```

## Notes

- `Prompt List` is configured as a value, so the space in the SharePoint list name is fine.
- `Prompt Id` and `Prompt Text` use internal names by default: `PromptId` and `PromptText`.
- Matching is exact and trims only the input parameter.

## References

- Microsoft Graph can retrieve a SharePoint site by hostname and server-relative path: https://learn.microsoft.com/en-us/graph/api/site-getbypath?view=graph-rest-1.0
- Microsoft Graph list items support `fields` expansion for SharePoint list columns: https://learn.microsoft.com/en-us/graph/api/listitem-list?view=graph-rest-1.0
- Selected SharePoint permissions require both Entra consent and an explicit resource permission grant: https://learn.microsoft.com/en-us/graph/permissions-selected-overview
