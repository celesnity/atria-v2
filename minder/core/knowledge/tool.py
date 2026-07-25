"""The agent-facing knowledge_query tool (core-owned ToolSpec)."""

from __future__ import annotations

from typing import Any, Callable

from minder.core.knowledge.categories import Category
from minder.core.skill_tools import ToolSpec


def build_knowledge_tool_spec(
    provider: Any, resolve_context: Callable[[], Any]
) -> ToolSpec:
    """Build the knowledge_query ToolSpec. tenant_id comes from resolve_context()."""

    def handler(question: str, category: str | None = None, k: int = 6) -> dict[str, Any]:
        filters = {"category": category} if category else {}
        results = provider.search(question, filters, k, resolve_context())
        return {"hits": [h.to_dict() for h in results.hits], "note": results.note}

    return ToolSpec(
        name="knowledge_query",
        description=(
            "Search the tenant's knowledge base (policies, PDFs, FAQs, workflows). "
            "Returns cited passages. Answer only from these; keep the citations."
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The user's question."},
                "category": {
                    "type": "string",
                    "enum": [c.value for c in Category],
                    "description": "Category to search (default reference_docs).",
                },
                "k": {"type": "integer", "description": "Max passages (default 6)."},
            },
            "required": ["question"],
        },
        handler=handler,
    )
