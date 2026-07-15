"""Unit tests for core consuming module declarative context."""
from __future__ import annotations

from minder.core.modules.remote import _enrich_description


def test_enrich_description_appends_when_to_use_and_examples():
    tool = {
        "name": "create_product",
        "description": "Create a product.",
        "when_to_use": "When the user provides SKU and price.",
        "examples": [{"sku": "A-1", "price": 9.9}],
    }
    out = _enrich_description(tool)
    assert "Create a product." in out
    assert "When to use: When the user provides SKU and price." in out
    assert '{"sku":"A-1","price":9.9}' in out


def test_enrich_description_plain_when_no_metadata():
    assert _enrich_description({"description": "Just a tool."}) == "Just a tool."
    assert _enrich_description({}) == ""


def test_read_module_context_merges_live_state_and_static(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready(
        "m", [{"name": "m_tool"}],
        context={"knowledge": ["K1"], "notes": [{"name": "a", "text": "t"}]},
    )
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)
    monkeypatch.setattr(
        remote.RemoteConnector, "fetch_context",
        lambda self, **kw: {"state": [{"name": "inv", "value": {"n": 2}}],
                            "ui_snapshot": {"page": "products"}},
    )

    class _Ctx:
        principal = {"username": "alice"}
        session_id = "s1"

    spec = remote.build_module_context_spec(_Ctx())
    assert spec.name == "read_module_context"
    out = spec.handler(module_name="m")
    assert out["success"] is True
    assert out["output"]["state"][0]["name"] == "inv"
    assert out["output"]["ui_snapshot"]["page"] == "products"
    assert out["output"]["knowledge"] == ["K1"]
    assert out["output"]["notes"] == [{"name": "a", "text": "t"}]


def test_read_module_context_unknown_module_is_soft_error(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="nope")
    assert out["success"] is False and "not reachable" in out["output"]
