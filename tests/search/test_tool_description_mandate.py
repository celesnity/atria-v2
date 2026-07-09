"""The knowledge_search schema text must mandate tool-first grounding and flat filters."""

import importlib.util
from pathlib import Path
from typing import Any

from atria.core.context_engineering.search.provider import SearchProvider
from atria.core.context_engineering.search.registry import SearchProviderRegistry
from atria.core.context_engineering.search.types import SearchContext, SourceResults

_TOOLS_PATH = Path(__file__).resolve().parents[2] / "modules" / "knowledge_search" / "tools.py"


class _DummyProvider(SearchProvider):
    name = "dummy"
    description = "Dummy source."
    filter_schema: dict[str, Any] = {"city": {"type": "string", "description": "City."}}

    def search(
        self, query: str, filters: dict[str, Any], limit: int, context: SearchContext
    ) -> SourceResults:
        return SourceResults(source=self.name, hits=[])


def _build_spec():
    spec = importlib.util.spec_from_file_location("knowledge_tools_under_test", _TOOLS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = SearchProviderRegistry()
    registry.register(_DummyProvider())
    return module.build_tool_spec(registry)


def test_description_mandates_tool_first_grounding():
    spec = _build_spec()
    assert "ONLY valid source" in spec.description
    assert "never answer from general knowledge" in spec.description


def test_description_says_filters_are_flat():
    spec = _build_spec()
    assert "FLAT object" in spec.description
    assert "do not nest" in spec.description
