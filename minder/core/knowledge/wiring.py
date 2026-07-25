"""Construct knowledge components from env; returns None when unavailable."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from minder.core.context_engineering.search.types import SearchContext

logger = logging.getLogger(__name__)


def _default_chat_fn() -> Callable[[list[dict]], str]:
    """Return a callable ``(messages: list[dict]) -> str`` over the app's LLM.

    Reads model/base-url from env as a last resort.  The correct production
    path is to resolve these from AppConfig / ``~/.minder/settings.json``;
    however, AppConfig is not available at wiring time (the registry is built
    before the HTTP request that carries the config), so we fall back to env
    vars here.  I4: prefer ``MINDER_MODEL`` over the hard-coded default, and
    align the fallback model with the app default (``gpt-4o``).

    Returns:
        A synchronous function that sends a list of chat messages and returns
        the assistant's text content.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url_raw = (
        os.environ.get("MINDER_API_BASE_URL")
        or os.environ.get("SEARCH_EMBED_BASE_URL", "").replace("/embeddings", "")
        or "https://api.openai.com/v1"
    )
    # Strip trailing /chat/completions — the SDK appends it automatically.
    if base_url_raw.endswith("/chat/completions"):
        base_url_raw = base_url_raw[: -len("/chat/completions")]

    # I4: align default with AppConfig.model default ("gpt-4o"), not "gpt-4o-mini".
    model = os.environ.get("MINDER_MODEL", "gpt-4o")

    def _chat(messages: list[dict]) -> str:
        try:
            from openai import OpenAI  # noqa: PLC0415

            client = OpenAI(api_key=api_key, base_url=base_url_raw)
            resp = client.chat.completions.create(model=model, messages=messages)
            return (resp.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("_default_chat_fn: LLM call failed: %s", exc)
            return ""

    return _chat


async def _knowledge_seed_and_drain() -> None:
    """Run seed scan then drain the ingestion queue (used by the scheduler)."""
    try:
        n = await arun_seed_scan()
        svc = await abuild_knowledge_service()
        processed = await svc.drain_queue()
        logger.info("knowledge seed+drain: enqueued=%d processed=%d", n, processed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("knowledge_seed_and_drain failed: %s", exc)


def _resolve_tenant(context: SearchContext) -> str | None:
    # Web threads identity via SearchContext.user_id → tenant map (future);
    # dev fallback lets local runs work without Keycloak.
    if os.environ.get("MINDER_ENV") == "dev":
        return os.environ.get("KNOWLEDGE_DEV_TENANT")
    return context.user_id


def build_knowledge_tool_spec_default() -> Any:
    """Build the default knowledge_query ToolSpec from env config.

    This runs on a worker thread (ToolRegistry init via RuntimeService) or in the
    CLI — both are off the event loop, so ``asyncio.run`` is safe here.

    Returns:
        ToolSpec if DATABASE_URL is set and all dependencies are available,
        None otherwise. Never raises — callers treat None as "feature unavailable".
    """
    if not os.environ.get("DATABASE_URL"):
        return None
    from minder.core.knowledge.embedding import KnowledgeEmbedder
    from minder.core.knowledge.graph import KnowledgeGraph
    from minder.core.knowledge.provider import DocumentsProvider
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.tool import build_knowledge_tool_spec
    from minder.db.connection import get_sessionmaker

    import asyncio

    # Safe: called from executor thread / CLI — no running event loop.
    sm = asyncio.run(get_sessionmaker())
    repo = KnowledgeRepository(sm)
    provider = DocumentsProvider(KnowledgeEmbedder(), repo, KnowledgeGraph(), _resolve_tenant)
    return build_knowledge_tool_spec(
        provider, lambda: SearchContext(os.environ.get("MINDER_SEARCH_USER_ID"))
    )


async def abuild_knowledge_service() -> Any:
    """Async variant of ``build_knowledge_service`` — safe inside a running loop.

    Returns:
        A KnowledgeService instance.
    """
    from minder.core.knowledge.embedding import KnowledgeEmbedder
    from minder.core.knowledge.graph import KnowledgeGraph
    from minder.core.knowledge.ingestion import IngestionService
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.service import KnowledgeService
    from minder.db.connection import get_sessionmaker

    sm = await get_sessionmaker()
    repo = KnowledgeRepository(sm)
    embedder = KnowledgeEmbedder()
    ingestion = IngestionService(repo, embedder, KnowledgeGraph(), _default_chat_fn())
    return KnowledgeService(repo, ingestion, embedder)


def build_knowledge_service() -> Any:
    """Sync variant of ``abuild_knowledge_service`` for CLI / off-loop contexts.

    Do NOT call from an async FastAPI handler or scheduler callback — use
    ``abuild_knowledge_service()`` there.

    Returns:
        A KnowledgeService instance. Never raises — callers should guard with
        try/except so a missing DB does not crash app startup.
    """
    import asyncio

    return asyncio.run(abuild_knowledge_service())


async def arun_seed_scan() -> int:
    """Async variant of ``run_seed_scan`` — safe inside a running loop.

    Returns:
        Number of documents enqueued by the scan. Returns 0 on error.
    """
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.seed import scan_seed_dir
    from minder.db.connection import get_sessionmaker

    root = os.environ.get("KNOWLEDGE_SEED_DIR", "")
    sm = await get_sessionmaker()
    return len(await scan_seed_dir(root, KnowledgeRepository(sm)))


def run_seed_scan() -> int:
    """Sync variant of ``arun_seed_scan`` for CLI / off-loop contexts.

    Do NOT call from an async FastAPI handler or scheduler callback — use
    ``arun_seed_scan()`` there.

    Returns:
        Number of documents enqueued by the scan. Returns 0 on error.
    """
    import asyncio

    return asyncio.run(arun_seed_scan())
