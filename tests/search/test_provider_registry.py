"""Unit tests for provider registry and filesystem module discovery."""

from pathlib import Path

from atria.core.context_engineering.search.provider import SearchProvider
from atria.core.context_engineering.search.registry import (
    SearchProviderRegistry,
    discover_module_providers,
)
from atria.core.context_engineering.search.types import SourceResults


class _StubProvider(SearchProvider):
    name = "stub"
    description = "stub provider"
    filter_schema = {"flag": {"type": "string"}}

    def search(self, query, filters, limit, context):
        return SourceResults(source=self.name, hits=[])


def test_registry_register_and_get():
    reg = SearchProviderRegistry()
    provider = _StubProvider()
    reg.register(provider)
    assert reg.get("stub") is provider
    assert reg.get("missing") is None
    assert reg.all() == [provider]


def test_discover_module_providers(tmp_path: Path):
    good = tmp_path / "good_mod"
    good.mkdir()
    (good / "search_provider.py").write_text(
        "from atria.core.context_engineering.search.provider import SearchProvider\n"
        "from atria.core.context_engineering.search.types import SourceResults\n"
        "class P(SearchProvider):\n"
        "    name = 'good'\n"
        "    description = 'd'\n"
        "    filter_schema = {}\n"
        "    def search(self, query, filters, limit, context):\n"
        "        return SourceResults(source='good', hits=[])\n"
        "def get_provider():\n"
        "    return P()\n",
        encoding="utf-8",
    )
    broken = tmp_path / "broken_mod"
    broken.mkdir()
    (broken / "search_provider.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    (tmp_path / "no_provider_mod").mkdir()

    reg = discover_module_providers(tmp_path)
    assert [p.name for p in reg.all()] == ["good"]
