# Dataverse MCP Server (Python)

MCP server for Microsoft Dataverse using the official Python SDK (`PowerPlatform-Dataverse-Client`).

This server is intentionally bulk-only and exposes tools to create, update, and delete many records at once.

## What this server provides

- `create_multiple`: create multiple rows in a Dataverse table and return created IDs.
- `update_multiple`: update multiple rows using the same payload.
- `delete_multiple`: delete multiple rows, using Dataverse bulk delete by default.

## Requirements

- Python `3.10+`
- Access to a Dataverse environment
- One of these auth options:
- Service principal (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`)
- Azure CLI login (`DATAVERSE_USE_AZURE_CLI=true` and `az login`)
- Interactive browser sign-in (fallback)

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
3. Else interactive browser auth is used.

The server loads `.env` from the current working directory.

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

## Environment variables

- `DATAVERSE_URL` required Dataverse org URL.
- `AZURE_TENANT_ID` optional for service principal auth.
- `AZURE_CLIENT_ID` optional for service principal auth.
- `AZURE_CLIENT_SECRET` optional for service principal auth.
- `DATAVERSE_USE_AZURE_CLI` optional (`true/false`), use Azure CLI auth when true.
- `MCP_TRANSPORT` optional transport (defaults to `stdio`).

## Security

- Do not commit `.env` or real credentials.
- This repo ignores `.env` files and tracks only `.env.example`.
