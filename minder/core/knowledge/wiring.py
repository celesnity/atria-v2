"""Construct knowledge components from env; returns None when unavailable."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from minder.core.context_engineering.search.types import SearchContext

logger = logging.getLogger(__name__)


def _default_chat_fn() -> Callable[[list[dict]], str]:
    """Return a callable ``(messages: list[dict]) -> str`` over the app's LLM.

    Reuses the OpenAI SDK with ``OPENAI_API_KEY`` and ``MINDER_API_BASE_URL``
    (falling back to the standard OpenAI endpoint when the env var is absent).

    Returns:
        A synchronous function that sends a list of chat messages and returns
        the assistant's text content.
    """
    import os

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url_raw = (
        os.environ.get("MINDER_API_BASE_URL")
        or os.environ.get("SEARCH_EMBED_BASE_URL", "").replace("/embeddings", "")
        or "https://api.openai.com/v1"
    )
    # Strip trailing /chat/completions — the SDK appends it automatically.
    if base_url_raw.endswith("/chat/completions"):
        base_url_raw = base_url_raw[: -len("/chat/completions")]

    model = os.environ.get("MINDER_MODEL", "gpt-4o-mini")

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
        n = run_seed_scan()
        svc = build_knowledge_service()
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

    sm = asyncio.run(get_sessionmaker())
    repo = KnowledgeRepository(sm)
    provider = DocumentsProvider(KnowledgeEmbedder(), repo, KnowledgeGraph(), _resolve_tenant)
    return build_knowledge_tool_spec(
        provider, lambda: SearchContext(os.environ.get("MINDER_SEARCH_USER_ID"))
    )


def build_knowledge_service() -> Any:
    """Build a KnowledgeService from env config.

    Returns:
        A KnowledgeService instance. Never raises — callers should guard with
        try/except so a missing DB does not crash app startup.
    """
    import asyncio

    from minder.core.knowledge.embedding import KnowledgeEmbedder
    from minder.core.knowledge.graph import KnowledgeGraph
    from minder.core.knowledge.ingestion import IngestionService
    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.service import KnowledgeService
    from minder.db.connection import get_sessionmaker

    sm = asyncio.run(get_sessionmaker())
    repo = KnowledgeRepository(sm)
    embedder = KnowledgeEmbedder()
    ingestion = IngestionService(repo, embedder, KnowledgeGraph(), _default_chat_fn())
    return KnowledgeService(repo, ingestion, embedder)


def run_seed_scan() -> int:
    """Run the knowledge seed scan and return the count of newly enqueued docs.

    Returns:
        Number of documents enqueued by the scan. Returns 0 on error.
    """
    import asyncio

    from minder.core.knowledge.repository import KnowledgeRepository
    from minder.core.knowledge.seed import scan_seed_dir
    from minder.db.connection import get_sessionmaker

    root = os.environ.get("KNOWLEDGE_SEED_DIR", "")

    async def _run() -> int:
        sm = await get_sessionmaker()
        return len(await scan_seed_dir(root, KnowledgeRepository(sm)))

    return asyncio.run(_run())
