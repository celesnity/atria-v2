"""Generic hybrid search framework: envelope, fusion, stores, providers."""

from minder.core.context_engineering.search.embedder import Embedder
from minder.core.context_engineering.search.fusion import facet_counts, rrf_fuse, top_margin
from minder.core.context_engineering.search.normalize import normalize_for_search, strip_diacritics
from minder.core.context_engineering.search.provider import SearchProvider
from minder.core.context_engineering.search.registry import (
    SearchProviderRegistry,
    discover_module_providers,
)
from minder.core.context_engineering.search.types import SearchContext, SearchHit, SourceResults

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
