"""Knowledge categories and their per-category ingestion/retrieval behavior."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Category(str, Enum):
    """The knowledge categories a document can belong to."""

    PERSONA = "persona"
    COMPANY_BACKGROUND = "company_background"
    REFERENCE_DOCS = "reference_docs"


@dataclass(frozen=True)
class CategoryBehavior:
    """How a category is treated.

    Attributes:
        inject: Summary is injected into the agent system prompt.
        build_graph: Chunks feed the Neo4j knowledge graph.
        summarize: The whole document is LLM-summarized on ingest.
    """

    inject: bool
    build_graph: bool
    summarize: bool


BEHAVIOR: dict[Category, CategoryBehavior] = {
    Category.PERSONA: CategoryBehavior(
        inject=True, build_graph=False, summarize=True
    ),
    Category.COMPANY_BACKGROUND: CategoryBehavior(
        inject=True, build_graph=False, summarize=True
    ),
    Category.REFERENCE_DOCS: CategoryBehavior(
        inject=False, build_graph=True, summarize=False
    ),
}


def is_valid_category(name: str) -> bool:
    """Return True if `name` is a known category value."""
    return name in Category._value2member_map_


def behavior_for(name: str) -> CategoryBehavior:
    """Return the behavior for a category value, raising ValueError if unknown."""
    if not is_valid_category(name):
        raise ValueError(f"Unknown knowledge category: {name!r}")
    return BEHAVIOR[Category(name)]
