"""Provider interface for the generic knowledge_search tool."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from atria.core.context_engineering.search.types import SearchContext, SourceResults


class SearchProvider(ABC):
    """A searchable domain source (documents, places, ...).

    Class attributes:
        name: Stable source key exposed in the tool's `source` enum.
        description: One-to-three sentences for the tool description; tell the
            agent what lives in this source and when to pick it.
        filter_schema: JSON-schema `properties` for this source's `filters`
            object. Only model-controllable relevance filters belong here —
            policy inputs (identity, permissions) are injected via
            SearchContext and must never appear in this schema.
    """

    name: str
    description: str
    filter_schema: dict[str, Any]

    @abstractmethod
    def search(
        self, query: str, filters: dict[str, Any], limit: int, context: SearchContext
    ) -> SourceResults:
        """Run a search and return the uniform envelope."""
