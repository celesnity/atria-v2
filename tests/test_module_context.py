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


def test_read_module_context_shapes_ui_and_merges_static(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready(
        "m",
        [{"name": "m_tool"}],
        context={"knowledge": ["K1"], "notes": [{"name": "a", "text": "t"}]},
    )
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)
    monkeypatch.setattr(
        remote.RemoteConnector,
        "fetch_context",
        lambda self, **kw: {
            "autonomy": "low",
            "principal": {"username": "alice", "authenticated": True, "roles": [], "scopes": []},
            "actions": [
                {
                    "name": "m_tool",
                    "risk": "low",
                    "read_only": True,
                    "reversible": True,
                    "undo": None,
                    "allowed": True,
                }
            ],
            "ui_snapshot": {
                "page": "products",
                "data": [{"name": "sku", "value": "A-1"}],
                "actions": [{"name": "save", "description": "Save"}],
            },
            "state": [{"name": "inv", "value": {"n": 2}}],
        },
    )

    class _Ctx:
        principal = {"username": "alice"}
        session_id = "s1"

    spec = remote.build_module_context_spec(_Ctx())
    assert spec.name == "read_module_context"
    out = spec.handler(module_name="m")
    assert out["success"] is True
    body = out["output"]
    assert body["page"] == "products"
    assert body["data"] == [{"name": "sku", "description": None, "value": "A-1"}]
    assert body["buttons"] == [{"name": "save", "description": "Save"}]
    assert body["actions"] == [
        {"name": "m_tool", "risk": "low", "read_only": True, "allowed": True}
    ]
    assert body["autonomy"] == "low"
    assert body["state"][0]["name"] == "inv"
    assert body["knowledge"] == ["K1"]
    assert body["notes"] == [{"name": "a", "text": "t"}]


def test_read_module_context_unknown_module_lists_live(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="produce", connector_url="http://p:9310")
    reg.mark_connector_ready("produce", [{"name": "cmd_x"}], context={})
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="nope")
    assert out["success"] is False
    assert "produce" in out["output"]


def test_read_module_context_empty_name_lists_live(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="produce", connector_url="http://p:9310")
    reg.mark_connector_ready("produce", [{"name": "cmd_x"}], context={})
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="")
    assert out["success"] is False
    assert "required" in out["output"] and "produce" in out["output"]


def test_read_module_context_no_live_modules(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="")
    assert out["success"] is False
    assert "No modules are currently live" in out["output"]
