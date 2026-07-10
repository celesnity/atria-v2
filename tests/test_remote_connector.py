"""Unit tests for the Atria-side remote connector client (httpx mocked)."""
from __future__ import annotations

import httpx
import pytest

from atria.core.modules import remote


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


from dataclasses import dataclass, field as _field


@dataclass
class _FakeManifestService:
    connector_url: str
    tools: list = _field(default_factory=list)
    health_path: str = "/connector/health"


@dataclass
class _FakeManifest:
    service: object = None


@dataclass
class _FakeModule:
    name: str
    manifest: object


def _module_with_tool():
    svc = _FakeManifestService(
        connector_url="http://mc:9200",
        tools=[{"name": "maintenance_copilot_query", "description": "q",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                               "required": ["query"]}}],
    )
    return _FakeModule("maintenance_copilot", _FakeManifest(service=svc))


def test_build_specs_registers_declared_tools(monkeypatch):
    from atria.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def fake_call(self, tool, arguments, timeout=110.0, principal=None):
        return {"success": True, "output": {"answer": "ok"},
                "card": {"answer": "ok", "review_required": False}, "llm_suffix": None}
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", fake_call)

    specs = remote.build_remote_tool_specs(ctx, [_module_with_tool()])
    assert [s.name for s in specs] == ["maintenance_copilot_query"]

    out = specs[0].handler(query="torque?")
    assert out["success"] is True
    assert out["output"]["answer"] == "ok"
    # No card_type in the response → broadcast under the generic "{module}_card"
    # type. A module names its own renderer by returning card_type explicitly.
    assert broadcasts == [
        {"type": "maintenance_copilot_card", "answer": "ok", "review_required": False}
    ]


def test_explicit_card_type_is_honored(monkeypatch):
    from atria.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def fake_call(self, tool, arguments, timeout=110.0, principal=None):
        return {"success": True, "output": {"answer": "ok"},
                "card": {"answer": "ok"}, "card_type": "maintenance_answer",
                "llm_suffix": None}
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", fake_call)

    specs = remote.build_remote_tool_specs(ctx, [_module_with_tool()])
    specs[0].handler(query="torque?")
    assert broadcasts[0]["type"] == "maintenance_answer"


def test_handler_connector_down_fails_closed(monkeypatch):
    from atria.core.skill_tools import SkillToolContext

    broadcasts = []
    ctx = SkillToolContext(broadcaster=broadcasts.append)

    def boom(self, tool, arguments, timeout=110.0, principal=None):
        raise remote.ConnectorUnreachable("refused")
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", boom)

    specs = remote.build_remote_tool_specs(ctx, [_module_with_tool()])
    out = specs[0].handler(query="torque?")
    assert out["success"] is True
    assert out["output"]["review_required"] is True
    assert "connector unreachable" in out["_llm_suffix"].lower()
    assert broadcasts[0]["type"] == "maintenance_copilot_card"


def test_module_without_service_yields_no_specs():
    from atria.core.skill_tools import SkillToolContext

    @dataclass
    class _NoSvc:
        service: object = None

    @dataclass
    class _Mod:
        name: str
        manifest: object

    specs = remote.build_remote_tool_specs(SkillToolContext(), [_Mod("plain", _NoSvc())])
    assert specs == []
