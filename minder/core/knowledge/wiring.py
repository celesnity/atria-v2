"""Construct knowledge components from env; returns None when unavailable."""

from __future__ import annotations

import os
from typing import Any

from minder.core.context_engineering.search.types import SearchContext


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
