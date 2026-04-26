from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(override=True)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    sharepoint_site_url: str
    list_name: str
    prompt_id_field: str = "PromptId"
    title_field: str = "Title"
    prompt_text_field: str = "PromptText"
    host: str = "0.0.0.0"
    port: int = 8000

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [
            name
            for name in (
                "AZURE_TENANT_ID",
                "AZURE_CLIENT_ID",
                "AZURE_CLIENT_SECRET",
                "SHAREPOINT_SITE_URL",
                "SHAREPOINT_LIST_NAME",
            )
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )

        return cls(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"],
            sharepoint_site_url=os.environ["SHAREPOINT_SITE_URL"],
            list_name=os.environ["SHAREPOINT_LIST_NAME"],
            prompt_id_field=os.getenv("PROMPT_ID_FIELD", "PromptId"),
            title_field=os.getenv("TITLE_FIELD", "Title"),
            prompt_text_field=os.getenv("PROMPT_TEXT_FIELD", "PromptText"),
            host=os.getenv("FASTMCP_HOST", "0.0.0.0"),
            port=int(os.getenv("FASTMCP_PORT", "8000")),
        )


class SharePointPromptClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._site_id: str | None = None
        self._list_id: str | None = None

    async def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        token_url = (
            "https://login.microsoftonline.com/"
            f"{quote(self.settings.tenant_id)}/oauth2/v2.0/token"
        )
        data = {
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "scope": GRAPH_SCOPE,
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            payload = response.json()

        self._access_token = payload["access_token"]
        return self._access_token

    async def _graph_get(
        self, path_or_url: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        token = await self._get_access_token()
        url = (
            path_or_url
            if path_or_url.startswith("https://")
            else f"{GRAPH_BASE_URL}{path_or_url}"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

    async def _get_site_id(self) -> str:
        if self._site_id:
            return self._site_id

        parsed = urlparse(self.settings.sharepoint_site_url)
        hostname = parsed.hostname
        if not hostname:
            raise RuntimeError("SHAREPOINT_SITE_URL must be an absolute SharePoint URL.")

        site_path = parsed.path.split("/Lists/", maxsplit=1)[0].rstrip("/")
        encoded_path = quote(site_path, safe="/")
        site = await self._graph_get(
            f"/sites/{hostname}:{encoded_path}", {"$select": "id,webUrl,displayName"}
        )
        self._site_id = site["id"]
        return self._site_id

    async def _get_list_id(self) -> str:
        if self._list_id:
            return self._list_id

        site_id = await self._get_site_id()
        lists = await self._graph_get(
            f"/sites/{site_id}/lists",
            {
                "$select": "id,displayName,webUrl",
                "$filter": f"displayName eq '{odata_escape(self.settings.list_name)}'",
            },
        )
        matches = lists.get("value", [])
        if not matches:
            raise RuntimeError(
                f"SharePoint list '{self.settings.list_name}' was not found on the site."
            )

        self._list_id = matches[0]["id"]
        return self._list_id

    async def _get_all_prompts(self) -> list[dict[str, Any]]:
        list_id = await self._get_list_id()
        site_id = await self._get_site_id()
        select_fields = ",".join(
            {
                self.settings.prompt_id_field,
                self.settings.title_field,
                self.settings.prompt_text_field,
            }
        )
        path_or_url = f"/sites/{site_id}/lists/{list_id}/items"
        params: dict[str, str] | None = {
            "$expand": f"fields($select={select_fields})",
            "$top": "200",
        }

        prompts: list[dict[str, Any]] = []
        while path_or_url:
            payload = await self._graph_get(path_or_url, params)
            prompts.extend(self._normalize_item(item) for item in payload.get("value", []))
            path_or_url = payload.get("@odata.nextLink")
            params = None

        return prompts

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        fields = item.get("fields", {})
        return {
            "item_id": item.get("id"),
            "web_url": item.get("webUrl"),
            "prompt_id": as_text(fields.get(self.settings.prompt_id_field)),
            "title": as_text(fields.get(self.settings.title_field)),
            "prompt_text": as_text(fields.get(self.settings.prompt_text_field)),
        }

    async def get_prompts_by_title(self, title: str) -> list[dict[str, Any]]:
        title_to_match = title.strip()
        return [
            prompt
            for prompt in await self._get_all_prompts()
            if prompt["title"] == title_to_match
        ]

    async def get_prompts_by_id(self, prompt_id: str) -> list[dict[str, Any]]:
        prompt_id_to_match = prompt_id.strip()
        return [
            prompt
            for prompt in await self._get_all_prompts()
            if prompt["prompt_id"] == prompt_id_to_match
        ]


def as_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "" if value is None else str(value)


def odata_escape(value: str) -> str:
    return value.replace("'", "''")


settings = Settings.from_env()
sharepoint = SharePointPromptClient(settings)
mcp = FastMCP(
    name="SharePoint Prompt MCP",
    instructions=(
        "Read prompt records from the configured SharePoint list. "
        "Each returned prompt contains prompt_id, title, prompt_text, item_id, and web_url."
    ),
    host=settings.host,
    port=settings.port,
    sse_path="/sse",
    message_path="/messages/",
)


@mcp.tool(name="GetPromptsByTitle")
async def get_prompts_by_title(
    title: Annotated[str, "Exact SharePoint Title value to match."],
) -> list[dict[str, Any]]:
    """Return all prompts whose SharePoint Title exactly matches the given title."""
    return await sharepoint.get_prompts_by_title(title)


@mcp.tool(name="GetPromptsById")
async def get_prompts_by_id(
    prompt_id: Annotated[str, "Exact Prompt Id column value to match."],
) -> list[dict[str, Any]]:
    """Return all prompts whose Prompt Id exactly matches the given value."""
    return await sharepoint.get_prompts_by_id(prompt_id)


if __name__ == "__main__":
    mcp.run(transport="sse")
