from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse


@dataclass
class BrowserUseResult:
    status: str
    summary: str
    duration_seconds: float


def _has_azure_config() -> bool:
    return bool(
        os.getenv("AZURE_OPENAI_ENDPOINT")
        and os.getenv("AZURE_OPENAI_API_KEY")
        and os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    )


def _normalize_azure_endpoint(raw: str | None) -> str | None:
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    return f"{parsed.scheme}://{parsed.netloc}/"


async def run_browser_use_summary(url: str, prompt: str | None = None) -> BrowserUseResult:
    start = datetime.now(timezone.utc)

    if not _has_azure_config() and not os.getenv("OPENAI_API_KEY") and not os.getenv("BROWSER_USE_API_KEY"):
        end = datetime.now(timezone.utc)
        return BrowserUseResult(
            status="skipped",
            summary=(
                "Skipped browser-use step because no model credentials were provided. "
                "Set Azure vars (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_NAME) "
                "or OPENAI_API_KEY."
            ),
            duration_seconds=(end - start).total_seconds(),
        )

    try:
        browser_use_module = importlib.import_module("browser_use")
        browser_use_llm_module = importlib.import_module("browser_use.llm")
        Agent = getattr(browser_use_module, "Agent")
        BrowserSession = getattr(browser_use_module, "BrowserSession")
        ChatOpenAI = getattr(browser_use_llm_module, "ChatOpenAI")
        ChatAzureOpenAI = getattr(browser_use_llm_module, "ChatAzureOpenAI")
    except Exception as exc:
        end = datetime.now(timezone.utc)
        return BrowserUseResult(
            status="failed",
            summary=f"browser-use imports failed: {exc}",
            duration_seconds=(end - start).total_seconds(),
        )

    browser_session = BrowserSession(
        headless=True,
        enable_default_extensions=False,
    )

    try:
        if _has_azure_config():
            endpoint = _normalize_azure_endpoint(os.getenv("AZURE_OPENAI_ENDPOINT"))
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "")
            llm = ChatAzureOpenAI(
                model=deployment,
                azure_endpoint=endpoint,
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                azure_deployment=deployment,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            )
        else:
            model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            llm = ChatOpenAI(model=model_name)

        task = prompt or f"Open {url}. Confirm what the page is about and return a concise summary with a confidence note."
        agent = Agent(task=task, llm=llm, browser_session=browser_session)
        history = await agent.run(max_steps=8)

        final_result = ""
        if hasattr(history, "final_result"):
            final = history.final_result()
            final_result = str(final) if final is not None else ""

        status = "passed" if final_result else "failed"
        summary = final_result or "Agent completed but returned no final_result output."
    except Exception as exc:
        status = "failed"
        summary = f"browser-use run failed: {exc}"
    finally:
        close_method = getattr(browser_session, "close", None)
        if callable(close_method):
            maybe_coro = close_method()
            if hasattr(maybe_coro, "__await__"):
                await maybe_coro

    end = datetime.now(timezone.utc)
    return BrowserUseResult(
        status=status,
        summary=summary,
        duration_seconds=(end - start).total_seconds(),
    )
