# Dataverse MCP Server (Python)

This project provides an MCP server backed by the official Microsoft Dataverse Python SDK (`PowerPlatform-Dataverse-Client`).

## 1. Install

```bash
pip install -e .
```

## 2. Configure environment variables

Copy `.env.example` and set values:

- `DATAVERSE_URL` (required) e.g. `https://yourorg.crm.dynamics.com`
- For service principal auth: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`
- Or set `DATAVERSE_USE_AZURE_CLI=true` to use `az login`
- Otherwise interactive browser auth is used

## 3. Run server

```bash
dataverse-mcp-server
```

Or:

```bash
python -m dataverse_mcp_server.server
```

## Available MCP tools

- `create_multiple`
- `update_multiple`
- `delete_multiple`

## Notes

- This server is intentionally bulk-only and does not expose unary create/update/delete tools.
