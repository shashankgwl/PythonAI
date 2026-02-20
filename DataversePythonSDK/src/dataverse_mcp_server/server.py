from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, ClientSecretCredential, InteractiveBrowserCredential
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from PowerPlatform.Dataverse.client import DataverseClient

mcp = FastMCP("DataverseBulkOperations", "1.0")

# Load environment variables from .env in current working directory or parents.
load_dotenv(dotenv_path=Path.cwd() / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


def _build_credential() -> TokenCredential:
    tenant_id = _env("AZURE_TENANT_ID")
    client_id = _env("AZURE_CLIENT_ID")
    client_secret = _env("AZURE_CLIENT_SECRET")

    if tenant_id and client_id and client_secret:
        return ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)

    if (_env("DATAVERSE_USE_AZURE_CLI", "false") or "").lower() in {"1", "true", "yes"}:
        return AzureCliCredential()

    return InteractiveBrowserCredential()


@lru_cache(maxsize=1)
def _client() -> DataverseClient:
    url = _env("DATAVERSE_URL")
    if not url:
        raise ValueError("DATAVERSE_URL is required, e.g. https://yourorg.crm.dynamics.com")

    return DataverseClient(url, _build_credential())


@mcp.tool(name="create_multiple",
          description="Create multiple records in a Dataverse table. Returns list of created record IDs." \
          "the input is a list of record data dictionaries, and the output is a list of created record IDs.")
def create_multiple(
    table: str,
    records: list[dict[str, object]],
) -> list[str]:
    """Create multiple records and return created IDs."""
    return _client().create(table, records)

@mcp.tool(name="update_multiple",
          description="Update multiple records in a Dataverse table by applying the same payload to each ID." \
          "the input is a list of record IDs and a data dictionary to apply to each record, and the output is a summary message indicating how many records were updated.")
def update_multiple(
    table: str,
    record_ids: list[str],
    data: dict[str, object],
) -> str:
    """Update multiple records by applying the same payload to each ID."""
    _client().update(table, record_ids, data)
    return f"Total number of records updated: {len(record_ids)}"


@mcp.tool(name="delete_multiple",
          description="Delete multiple records in a Dataverse table by ID, defaulting to bulk delete for efficiency.")
def delete_multiple(
    table: str,
    record_ids: list[str],
    use_bulk_delete: bool = True,
) -> str:
    """Delete multiple records, defaulting to Dataverse bulk delete."""
    _client().delete(table, record_ids, use_bulk_delete=use_bulk_delete)
    return f"Total number of records deleted: {len(record_ids)}"


def main() -> None:
    transport = _env("MCP_TRANSPORT", "stdio") or "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
