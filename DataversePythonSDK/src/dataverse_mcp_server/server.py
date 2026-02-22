from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from azure.core.credentials import TokenCredential
from azure.identity import AzureCliCredential, ClientSecretCredential
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
from PowerPlatform.Dataverse.client import DataverseClient
from starlette.responses import JSONResponse


def _configure_logging() -> logging.Logger:
    level_name = (os.getenv("LOG_LEVEL", "INFO") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logger = logging.getLogger("dataverse_mcp_server")
    logger.info("Logging configured with level=%s", logging.getLevelName(level))
    return logger


# Load environment variables from a .env file. Search in CWD and this file's ancestor dirs.
def _find_and_load_dotenv() -> None:
    # Candidates: current working directory and this file's directory
    candidates = [Path.cwd(), Path(__file__).resolve().parent]
    for base in candidates:
        for p in (base,) + tuple(base.parents):
            env_file = p / ".env"
            if env_file.exists():
                load_dotenv(dotenv_path=env_file)
                return
    # Fallback to default behavior (will look in CWD)
    load_dotenv()


_find_and_load_dotenv()
logger = _configure_logging()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None or value == "":
        return default
    return int(value)


def _server_host() -> str:
    return (
        _env("FASTMCP_HOST")
        or _env("HOST")
        or "0.0.0.0"
    )


def _server_port() -> int:
    fastmcp_port = _env("FASTMCP_PORT")
    if fastmcp_port:
        return int(fastmcp_port)
    return _env_int("PORT", 8550)


def _streamable_path() -> str:
    return (
        _env("FASTMCP_STREAMABLE_HTTP_PATH")
        or _env("MCP_PATH")
        or "/mcp"
    )


mcp = FastMCP(
    "DataverseBulkOperations",
    "1.0",
    host=_server_host(),
    port=_server_port(),
    streamable_http_path=_streamable_path(),
)


def _build_credential() -> TokenCredential:
    tenant_id = _env("AZURE_TENANT_ID")
    client_id = _env("AZURE_CLIENT_ID")
    client_secret = _env("AZURE_CLIENT_SECRET")

    if tenant_id and client_id and client_secret:
        logger.info("Using ClientSecretCredential for Dataverse authentication")
        return ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)

    if (_env("DATAVERSE_USE_AZURE_CLI", "false") or "").lower() in {"1", "true", "yes"}:
        logger.info("Using AzureCliCredential for Dataverse authentication")
        return AzureCliCredential()

    logger.error("Dataverse authentication configuration is incomplete")
    raise ValueError(
        "Provide AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET, "
        "or set DATAVERSE_USE_AZURE_CLI=true."
    )


@lru_cache(maxsize=1)
def _client() -> DataverseClient:
    url = _env("DATAVERSE_URL")
    if not url:
        logger.error("DATAVERSE_URL is not configured")
        raise ValueError("DATAVERSE_URL is required, e.g. https://orgeaf9224a.crm.dynamics.com/")

    logger.info("Creating DataverseClient for url=%s", url)
    return DataverseClient(url, _build_credential())

@mcp.custom_route("/health", methods=["GET"])
def health_check(request) -> JSONResponse:
    logger.info("Health check requested")
    return JSONResponse({"status": "ok", "connectedto" : _env("DATAVERSE_URL")})
   

@mcp.tool(name="create_multiple",
          description="Create multiple records in a Dataverse table. Returns list of created record IDs." \
          "the input is a list of record data dictionaries, and the output is a list of created record IDs.")
def create_multiple(
    table: str,
    records: list[dict[str, object]],
) -> list[str]:
    """Create multiple records and return created IDs."""
    logger.info("create_multiple started table=%s records=%d", table, len(records))
    created_ids = _client().create(table, records)
    logger.info("create_multiple completed table=%s created=%d", table, len(created_ids))
    return created_ids

@mcp.tool(name="update_multiple",
          description="Update multiple records in a Dataverse table by applying the same payload to each ID." \
          "the input is a list of record IDs and a data dictionary to apply to each record, and the output is a summary message indicating how many records were updated.")
def update_multiple(
    table: str,
    record_ids: list[str],
    data: dict[str, object],
) -> str:
    """Update multiple records by applying the same payload to each ID."""
    logger.info("update_multiple started table=%s records=%d", table, len(record_ids))
    _client().update(table, record_ids, data)
    logger.info("update_multiple completed table=%s updated=%d", table, len(record_ids))
    return f"Total number of records updated: {len(record_ids)}"

@mcp.tool(name="create_table",
          description="Create a new Dataverse table with specified columns. " \
          "The input is the table name and a dictionary of column names and types, and the output is a confirmation message.")
def create_table(table:str, columns : dict[str,any]) -> str:
    """Create a new Dataverse table with specified columns."""
    logger.info("create_table started table=%s columns=%d", table, len(columns))
    _client().tables.create(table=table,columns=columns)
    logger.info("create_table completed table=%s", table)
    return f"Table '{table}' created with columns: {', '.join(columns.keys())}"

@mcp.tool(name="delete_multiple",
          description="Delete multiple records in a Dataverse table by ID, defaulting to bulk delete for efficiency.")
def delete_multiple(
    table: str,
    record_ids: list[str],
    use_bulk_delete: bool = True,
) -> str:
    """Delete multiple records, defaulting to Dataverse bulk delete."""
    logger.info(
        "delete_multiple started table=%s records=%d use_bulk_delete=%s",
        table,
        len(record_ids),
        use_bulk_delete,
    )
    _client().delete(table, record_ids, use_bulk_delete=use_bulk_delete)
    logger.info("delete_multiple completed table=%s deleted=%d", table, len(record_ids))
    return f"Total number of records deleted: {len(record_ids)}"


def main() -> None:
    transport = _env("MCP_TRANSPORT", "streamable-http") or "streamable-http"
    logger.info(
        "Starting Dataverse MCP server host=%s port=%s transport=%s path=%s",
        _server_host(),
        _server_port(),
        transport,
        _streamable_path(),
    )
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
