# Dataverse MCP Server (Python)

MCP server for Microsoft Dataverse using the official Python SDK (`PowerPlatform-Dataverse-Client`).

This server is intentionally bulk-focused and exposes tools for Dataverse table creation plus high-volume create, update, and delete operations.

## What this server provides

- `create_multiple`: create multiple rows in a Dataverse table and return created IDs.
- `update_multiple`: update multiple rows using the same payload.
- `create_table`: create a Dataverse table with provided columns.
- `delete_multiple`: delete multiple rows, using Dataverse bulk delete by default.
- `GET /health`: basic health endpoint that returns status and configured Dataverse URL.

## Requirements

- Python `3.10+`
- Access to a Dataverse environment
- One of these auth options:
- Service principal (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`)
- Azure CLI login (`DATAVERSE_USE_AZURE_CLI=true` and `az login`)

## Installation

From the repo root:

```bash
pip install -e .
```

## Configuration

1. Copy `.env.example` to `.env`.
2. Set values for your environment.

Minimum required variable:

- `DATAVERSE_URL` (example: `https://yourorg.crm.dynamics.com`)

Authentication behavior:

1. If `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are all set, service principal auth is used.
2. Else if `DATAVERSE_USE_AZURE_CLI=true`, Azure CLI auth is used.
3. Else startup fails with a configuration error.

The server loads `.env` by searching from:
- current working directory and its parent folders
- this module directory and its parent folders

## Run

Using installed entrypoint:

```bash
dataverse-mcp-server
```

Or module mode:

```bash
python -m dataverse_mcp_server.server
```

Or PowerShell helper script:

```powershell
./run.ps1
```

### Docker / Azure Container Apps

The included `Dockerfile` runs the server with:
- `MCP_TRANSPORT=streamable-http`
- `FASTMCP_HOST=0.0.0.0`
- `FASTMCP_PORT=8550`

Port `8550` is exposed.

## Environment variables

- `DATAVERSE_URL` required Dataverse org URL.
- `AZURE_TENANT_ID` optional for service principal auth.
- `AZURE_CLIENT_ID` optional for service principal auth.
- `AZURE_CLIENT_SECRET` optional for service principal auth.
- `DATAVERSE_USE_AZURE_CLI` optional (`true/false`), use Azure CLI auth when true.
- `MCP_TRANSPORT` optional transport (defaults to `streamable-http`).
- `FASTMCP_HOST` optional server bind host (defaults to `0.0.0.0`).
- `FASTMCP_PORT` optional server port (defaults to `8550`; falls back to `PORT` if unset).
- `FASTMCP_STREAMABLE_HTTP_PATH` optional streamable HTTP path (defaults to `/mcp`; alias: `MCP_PATH`).
- `HOST` optional alias for `FASTMCP_HOST`.
- `PORT` optional fallback port if `FASTMCP_PORT` is not set.
- `LOG_LEVEL` optional Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, etc.; default `INFO`).

## Security

- Do not commit `.env` or real credentials.
- This repo ignores `.env` files and tracks only `.env.example`.
