"""Unit tests for the Minder-side remote connector client (httpx mocked)."""
from __future__ import annotations

from dataclasses import dataclass

import httpx
import pytest

from minder.core.modules import remote


def _connector(handler):
    transport = httpx.MockTransport(handler)
    conn = remote.RemoteConnector("maintenance_copilot", "http://mc:9200")
    conn._client = httpx.Client(transport=transport, base_url="http://mc:9200")
    return conn


def test_call_tool_returns_connector_payload():
    def handler(request):
        assert request.url.path == "/connector/tools/maintenance_copilot_query"
        return httpx.Response(200, json={"success": True, "output": {"answer": "42"},
                                         "card": {"answer": "42"}, "llm_suffix": None})
    conn = _connector(handler)
    out = conn.call_tool("maintenance_copilot_query", {"query": "q"})
    assert out["card"]["answer"] == "42"


def test_autonomy_maps_to_ladder_and_rides_the_header():
    # core mode → connector risk ladder (only risky actions gate; routine work runs)
    assert remote._ladder_autonomy("Manual") == "medium"    # gates high/critical (e.g. delete)
    assert remote._ladder_autonomy("Semi-Auto") == "high"   # gates critical only
    assert remote._ladder_autonomy("Auto") == "critical"    # gates nothing
    assert remote._ladder_autonomy("weird") is None         # unknown ⇒ module default

    # the header carries the mapped value
    seen2 = {}

    def h2(request):
        seen2["a"] = request.headers.get("X-Minder-Autonomy")
        return httpx.Response(200, json={"success": True, "output": "ok"})

    _connector(h2).call_tool("t", {}, autonomy="Manual")
    assert seen2["a"] == "medium"

    seen = {}

    def handler(request):
        seen["autonomy"] = request.headers.get("X-Minder-Autonomy")
        return httpx.Response(200, json={"success": True, "output": "ok"})

    conn = _connector(handler)
    conn.call_tool("t", {}, autonomy="Semi-Auto")
    assert seen["autonomy"] == "high"
    # no autonomy ⇒ no header (module uses its own default_autonomy)
    conn.call_tool("t", {})
    assert seen["autonomy"] is None


def test_requires_approval_forces_stop_suffix_and_flag():
    # A gated packet must be flagged and carry the firm "approve on the card" suffix
    # so the agent never routes approval through a channel — even if the module's
    # own suffix was weak/absent.
    ctx = type("Ctx", (), {"push_block": None, "broadcaster": None, "logger": remote.logger})()
    out = remote._emit_response(ctx, _connector(lambda r: None),
                                {"success": True, "output": "proposing…",
                                 "requires_approval": True, "card": {"kind": "decision"}})
    assert out["requires_approval"] is True
    assert "on-screen card IS the approval" in out["_llm_suffix"]
    assert "Do NOT send a message" in out["_llm_suffix"]


def test_call_tool_network_error_raises_unreachable():
    def handler(request):
        raise httpx.ConnectError("refused")
    conn = _connector(handler)
    with pytest.raises(remote.ConnectorUnreachable):
        conn.call_tool("maintenance_copilot_query", {"query": "q"})


def test_is_healthy_true_on_200():
    def handler(request):
        assert request.url.path == "/connector/health"
        return httpx.Response(200, json={"ok": True})
    assert _connector(handler).is_healthy() is True


def test_is_healthy_false_on_error():
    def handler(request):
        raise httpx.ConnectError("refused")
    assert _connector(handler).is_healthy() is False


def test_unavailable_card_is_fail_closed_plain_dict():
    card = remote.unavailable_card("q", "maintenance_copilot")
    assert card["review_required"] is True
    assert card["confidence"] == 0.0
    assert card["confidence_band"] == "low"
    assert card["citations"] == []


@pytest.fixture(autouse=True)
def _reset_module_registry():
    """Isolate every test from registry state left by a previous test."""
    from minder.core.modules.registry import reset_registry_for_tests
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def _ready_registry(monkeypatch, tmp_path):
    """Register and ready a maintenance_copilot connector in a fresh registry."""
    from minder.core.modules.registry import reset_registry_for_tests, get_registry
    reset_registry_for_tests()
    monkeypatch.setenv("MINDER_MODULES_DIR", str(tmp_path))
    reg = get_registry()
    reg.register_connector(name="maintenance_copilot", connector_url="http://mc:9200")
    reg.mark_connector_ready("maintenance_copilot", [
        {"name": "maintenance_copilot_query", "description": "q",
         "parameters": {"type": "object",
                        "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    ])
    return reg


def test_build_specs_registers_declared_tools(monkeypatch, tmp_path):
    from minder.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def fake_call(self, tool, arguments, timeout=110.0, principal=None, session_id=None, autonomy=None):
        return {"success": True, "output": {"answer": "ok"},
                "card": {"answer": "ok", "review_required": False}, "llm_suffix": None}
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", fake_call)

    reg = _ready_registry(monkeypatch, tmp_path)
    specs = remote.build_remote_tool_specs(ctx, reg.live_service_modules())
    # A live connector also gets the module-context reader appended.
    assert [s.name for s in specs] == ["maintenance_copilot_query", "read_module_context"]

    out = specs[0].handler(query="torque?")
    assert out["success"] is True
    assert out["output"]["answer"] == "ok"
    # No card_type in the response → broadcast under the generic "{module}_card"
    # type. A module names its own renderer by returning card_type explicitly.
    assert broadcasts == [
        {"type": "maintenance_copilot_card", "answer": "ok", "review_required": False}
    ]


def test_explicit_card_type_is_honored(monkeypatch, tmp_path):
    from minder.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def fake_call(self, tool, arguments, timeout=110.0, principal=None, session_id=None, autonomy=None):
        return {"success": True, "output": {"answer": "ok"},
                "card": {"answer": "ok"}, "card_type": "maintenance_answer",
                "llm_suffix": None}
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", fake_call)

    reg = _ready_registry(monkeypatch, tmp_path)
    specs = remote.build_remote_tool_specs(ctx, reg.live_service_modules())
    specs[0].handler(query="torque?")
    assert broadcasts[0]["type"] == "maintenance_answer"


def test_handler_connector_down_fails_closed(monkeypatch, tmp_path):
    from minder.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def boom(self, tool, arguments, timeout=110.0, principal=None, session_id=None, autonomy=None):
        raise remote.ConnectorUnreachable("refused")
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", boom)

    reg = _ready_registry(monkeypatch, tmp_path)
    specs = remote.build_remote_tool_specs(ctx, reg.live_service_modules())
    out = specs[0].handler(query="torque?")
    assert out["success"] is True
    assert out["output"]["review_required"] is True
    assert "connector unreachable" in out["_llm_suffix"].lower()
    assert broadcasts[0]["type"] == "maintenance_copilot_card"


def test_module_without_service_yields_no_specs():
    from minder.core.skill_tools import SkillToolContext

    @dataclass
    class _NoSvc:
        service: object = None

    @dataclass
    class _Mod:
        name: str
        manifest: object

    specs = remote.build_remote_tool_specs(SkillToolContext(), [_Mod("plain", _NoSvc())])
    assert specs == []


def test_fetch_context_returns_state_payload():
    def handler(request):
        assert request.url.path == "/connector/context"
        return httpx.Response(200, json={
            "state": [{"name": "inventory", "value": {"total": 2}}],
            "ui_snapshot": {"page": "products"},
            "actions": [],
        })
    conn = _connector(handler)
    out = conn.fetch_context()
    assert out["state"][0]["name"] == "inventory"
    assert out["ui_snapshot"]["page"] == "products"


def test_fetch_context_returns_none_on_error():
    def handler(request):
        return httpx.Response(503, json={"error": "down"})
    conn = _connector(handler)
    assert conn.fetch_context() is None
