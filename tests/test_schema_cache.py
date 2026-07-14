"""ToolSchemaBuilder caches its assembled schema list (no per-call deepcopy)."""

from minder.core.agents.components.schemas.normal_builder import ToolSchemaBuilder


class _Reg:
    """Minimal registry stub: no MCP tools, no subagent manager."""

    _handlers: dict = {}

    def get_discovered_mcp_tools(self):
        return set()


def test_build_is_cached_between_calls():
    b = ToolSchemaBuilder(_Reg())
    first = b.build()
    second = b.build()
    # Same inputs -> identical object returned from cache (not a fresh deepcopy).
    assert first is second
    assert isinstance(first, list) and first, "schemas must be non-empty"


def test_cache_invalidates_when_disabled_set_changes(monkeypatch):
    import minder.core.agents.components.schemas.normal_builder as nb

    monkeypatch.setattr(nb, "load_disabled_tools", lambda: set())
    b = ToolSchemaBuilder(_Reg())
    first = b.build()
    names_before = {s["function"]["name"] for s in first}

    # Pick any builtin name and disable it; cache must rebuild and drop it.
    victim = next(iter(names_before))
    monkeypatch.setattr(nb, "load_disabled_tools", lambda: {victim})
    second = b.build()
    assert second is not first
    assert victim not in {s["function"]["name"] for s in second}
