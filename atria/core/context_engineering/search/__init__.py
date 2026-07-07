"""Generic hybrid search framework: envelope, fusion, stores, providers."""

from atria.core.context_engineering.search.embedder import Embedder
from atria.core.context_engineering.search.fusion import facet_counts, rrf_fuse, top_margin
from atria.core.context_engineering.search.normalize import normalize_for_search, strip_diacritics
from atria.core.context_engineering.search.provider import SearchProvider
from atria.core.context_engineering.search.registry import (
    SearchProviderRegistry,
    discover_module_providers,
)
from atria.core.context_engineering.search.types import SearchContext, SearchHit, SourceResults

__all__ = [
    "Embedder",
    "SearchContext",
    "SearchHit",
    "SearchProvider",
    "SearchProviderRegistry",
    "SourceResults",
    "discover_module_providers",
    "facet_counts",
    "normalize_for_search",
    "rrf_fuse",
    "strip_diacritics",
    "top_margin",
]
