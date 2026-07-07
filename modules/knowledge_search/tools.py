"""Registers the generic knowledge_search tool over discovered providers."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from atria.core.context_engineering.search.registry import (
    SearchProviderRegistry,
    discover_module_providers,
)
from atria.core.context_engineering.search.types import SearchContext
from atria.core.skill_tools import SkillToolContext, ToolSpec

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 8
_MAX_LIMIT = 20


def build_tool_spec(registry: SearchProviderRegistry) -> ToolSpec | None:
    """Compose the knowledge_search ToolSpec from registered providers.

    Args:
        registry: SearchProviderRegistry containing registered providers.

    Returns:
        ToolSpec if providers exist, None otherwise.
    """
    providers = registry.all()
    if not providers:
        return None

    source_lines = [f"- `{p.name}`: {p.description}" for p in providers]
    filter_docs = {p.name: p.filter_schema for p in providers}
    description = (
        "Hybrid (lexical + semantic) search over domain knowledge sources. "
        "Choose `source` by intent:\n"
        + "\n".join(source_lines)
        + "\n\nPer-source `filters` properties:\n"
        + json.dumps(filter_docs, ensure_ascii=False, indent=1)
        + "\n\nResults include `facets` (valid filter values) and `top_margin` "
        "(low margin across distinct candidates => ask the user to clarify)."
    )

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language query (Vietnamese or English).",
            },
            "source": {
                "type": "string",
                "enum": [p.name for p in providers],
                "description": "Knowledge source to search.",
            },
            "filters": {
                "type": "object",
                "description": (
                    "Optional structured filters. Per-source schemas:\n"
                    + json.dumps(filter_docs, ensure_ascii=False)
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"Max hits (default {_DEFAULT_LIMIT}).",
            },
        },
        "required": ["query", "source"],
    }

    def _handler(
        query: str,
        source: str,
        filters: dict[str, Any] | None = None,
        limit: int = _DEFAULT_LIMIT,
        **_ignored: Any,
    ) -> dict[str, Any]:
        """Execute a knowledge search with defensive limit parsing."""
        provider = registry.get(source)
        if provider is None:
            known = ", ".join(sorted(p.name for p in registry.all()))
            return {
                "success": False,
                "error": f"Unknown source {source!r}. Known sources: {known}",
                "output": None,
            }
        # single-user env mechanism — never set per-request in a shared process
        # (cross-user ACL identity race); web identity plumbing is a tracked
        # follow-up
        context = SearchContext(user_id=os.environ.get("ATRIA_SEARCH_USER_ID") or None)
        try:
            bounded = max(1, min(int(limit), _MAX_LIMIT))
        except (TypeError, ValueError):
            bounded = _DEFAULT_LIMIT
        try:
            results = provider.search(query, filters or {}, bounded, context)
        except Exception as exc:  # noqa: BLE001
            logger.exception("knowledge_search provider %r failed", source)
            return {
                "success": False,
                "error": f"{source} search failed: {exc}",
                "output": None,
            }
        return {
            "success": True,
            "output": json.dumps(results.to_dict(), ensure_ascii=False),
        }

    return ToolSpec(
        name="knowledge_search",
        description=description,
        parameters=parameters,
        handler=_handler,
    )


def register(ctx: SkillToolContext) -> list[ToolSpec]:
    """Skill-tool entry point: discover providers, expose one tool.

    Args:
        ctx: SkillToolContext from the skill-tool framework.

    Returns:
        List containing the knowledge_search ToolSpec if providers exist,
        empty list otherwise.
    """
    from atria.core.modules.registry import resolve_modules_root

    registry = discover_module_providers(resolve_modules_root())
    spec = build_tool_spec(registry)
    if spec is None:
        logger.info("knowledge_search: no providers discovered; " "tool not registered")
        return []
    return [spec]
