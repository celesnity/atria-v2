"""Tests for the knowledge_search hub tool spec and dispatch."""

import importlib.util
import json
from pathlib import Path

from minder.core.context_engineering.search.provider import SearchProvider
from minder.core.context_engineering.search.registry import SearchProviderRegistry
from minder.core.context_engineering.search.types import SearchHit, SourceResults

_TOOLS_PATH = Path(__file__).resolve().parents[2] / "modules" / "knowledge_search" / "tools.py"


def _load_tools_module():
    spec = importlib.util.spec_from_file_location("ks_tools_under_test", _TOOLS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _EchoProvider(SearchProvider):
    name = "echo"
    description = "Echo provider for tests."
    filter_schema = {"tag": {"type": "string", "description": "tag filter"}}

    def __init__(self):
        self.seen = None

    def search(self, query, filters, limit, context):
        self.seen = (query, filters, limit, context.user_id)
        hit = SearchHit(id="e1", source="echo", title=query, snippet="", score=1.0)
        return SourceResults(source="echo", hits=[hit], top_margin=1.0)


def test_build_tool_spec_composes_sources_and_filters():
    module = _load_tools_module()
    registry = SearchProviderRegistry()
    registry.register(_EchoProvider())
    spec = module.build_tool_spec(registry)
    assert spec.name == "knowledge_search"
    props = spec.parameters["properties"]
    assert props["source"]["enum"] == ["echo"]
    assert "tag filter" in json.dumps(spec.parameters, ensure_ascii=False)
    assert spec.parameters["required"] == ["query", "source"]
    assert "echo" in spec.description


def test_build_tool_spec_returns_none_without_providers():
    module = _load_tools_module()
    assert module.build_tool_spec(SearchProviderRegistry()) is None


def test_handler_dispatches_and_serializes(monkeypatch):
    module = _load_tools_module()
    registry = SearchProviderRegistry()
    provider = _EchoProvider()
    registry.register(provider)
    spec = module.build_tool_spec(registry)
    monkeypatch.setenv("MINDER_SEARCH_USER_ID", "U042")
    result = spec.handler(query="cà phê", source="echo", filters={"tag": "x"}, limit=3)
    assert result["success"] is True
    payload = json.loads(result["output"])
    assert payload["hits"][0]["title"] == "cà phê"
    assert provider.seen == ("cà phê", {"tag": "x"}, 3, "U042")


def test_handler_unknown_source_is_error():
    module = _load_tools_module()
    registry = SearchProviderRegistry()
    registry.register(_EchoProvider())
    spec = module.build_tool_spec(registry)
    result = spec.handler(query="q", source="nope")
    assert result["success"] is False
    assert "nope" in result["error"]
