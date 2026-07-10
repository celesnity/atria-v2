"""Tests that _make_handler forwards X-Atria-Session and X-Atria-Principal
to the connector via call_tool, using httpx MockTransport to capture headers."""
from __future__ import annotations

import json

import httpx
import pytest

from atria.core.modules import remote
from atria.core.modules.remote import RemoteConnector, _make_handler
from atria.core.skill_tools import SkillToolContext


def _connector_with_capture(captured: list) -> RemoteConnector:
    """Build a RemoteConnector backed by a MockTransport that records requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "output": {"answer": "ok"},
                "card": {"answer": "ok", "review_required": False},
                "llm_suffix": None,
            },
        )

    transport = httpx.MockTransport(handler)
    conn = RemoteConnector("test_module", "http://test-module:9300")
    conn._client = httpx.Client(transport=transport, base_url="http://test-module:9300")
    return conn


@pytest.fixture(autouse=True)
def _reset_registry():
    from atria.core.modules.registry import reset_registry_for_tests
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def _ready_registry(monkeypatch, tmp_path, *, streaming: bool = False):
    from atria.core.modules.registry import reset_registry_for_tests, get_registry

    reset_registry_for_tests()
    monkeypatch.setenv("ATRIA_MODULES_DIR", str(tmp_path))
    reg = get_registry()
    reg.register_connector(name="test_module", connector_url="http://test-module:9300")
    tool_spec: dict = {
        "name": "test_tool",
        "description": "test",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }
    if streaming:
        tool_spec["streaming"] = True
    reg.mark_connector_ready("test_module", [tool_spec])
    return reg


class TestMakeHandlerForwardsIdentity:
    """_make_handler non-stream path must set X-Atria-Session and X-Atria-Principal."""

    def test_session_and_principal_forwarded(self, monkeypatch, tmp_path):
        captured: list[httpx.Request] = []
        conn = _connector_with_capture(captured)

        ctx = SkillToolContext(broadcaster=lambda _: None)
        ctx.session_id = "sess-1"
        ctx.principal = {"username": "alice", "email": "a@x"}

        handler = _make_handler(ctx, conn, "test_tool", streaming=False)
        result = handler(query="hello")

        assert result["success"] is True
        assert len(captured) == 1
        req = captured[0]
        assert req.headers.get("x-atria-session") == "sess-1"
        principal_header = req.headers.get("x-atria-principal")
        assert principal_header is not None
        decoded = json.loads(principal_header)
        assert decoded["username"] == "alice"
        assert decoded["email"] == "a@x"

    def test_no_session_omits_header(self, monkeypatch, tmp_path):
        captured: list[httpx.Request] = []
        conn = _connector_with_capture(captured)

        ctx = SkillToolContext(broadcaster=lambda _: None)
        ctx.session_id = None
        ctx.principal = None

        handler = _make_handler(ctx, conn, "test_tool", streaming=False)
        handler(query="hello")

        req = captured[0]
        assert "x-atria-session" not in req.headers
        assert "x-atria-principal" not in req.headers

    def test_session_forwarded_via_build_remote_tool_specs(self, monkeypatch, tmp_path):
        """End-to-end: build_remote_tool_specs → handler → connector request carries headers."""
        captured: list[httpx.Request] = []

        ctx = SkillToolContext(broadcaster=lambda _: None)
        ctx.session_id = "sess-1"
        ctx.principal = {"username": "alice", "email": "a@x"}

        reg = _ready_registry(monkeypatch, tmp_path)

        # Patch RemoteConnector.call_tool to use our capturing connector instead
        original_init = RemoteConnector.__init__

        def patched_init(self, name, connector_url, health_path="/connector/health"):
            original_init(self, name, connector_url, health_path)
            transport = httpx.MockTransport(
                lambda req: (captured.append(req), httpx.Response(
                    200,
                    json={"success": True, "output": {"answer": "ok"},
                          "card": {"answer": "ok", "review_required": False},
                          "llm_suffix": None},
                ))[1]
            )
            self._client = httpx.Client(transport=transport, base_url=connector_url)

        monkeypatch.setattr(RemoteConnector, "__init__", patched_init)

        specs = remote.build_remote_tool_specs(ctx, reg.live_service_modules())
        assert len(specs) == 1

        specs[0].handler(query="hello")

        assert len(captured) == 1
        req = captured[0]
        assert req.headers.get("x-atria-session") == "sess-1"
        principal_header = req.headers.get("x-atria-principal")
        assert principal_header is not None
        decoded = json.loads(principal_header)
        assert decoded["username"] == "alice"


class TestAuthHeaders:
    """Unit tests for _auth_headers session_id parameter."""

    def test_session_id_set_when_provided(self):
        headers = remote._auth_headers("mod", None, session_id="s-42")
        assert headers["X-Atria-Session"] == "s-42"

    def test_session_id_absent_when_none(self):
        headers = remote._auth_headers("mod", None, session_id=None)
        assert "X-Atria-Session" not in headers

    def test_principal_and_session_both_present(self):
        headers = remote._auth_headers(
            "mod",
            {"username": "bob"},
            session_id="s-99",
        )
        assert headers["X-Atria-Session"] == "s-99"
        decoded = json.loads(headers["X-Atria-Principal"])
        assert decoded["username"] == "bob"


class TestCallToolSessionId:
    """RemoteConnector.call_tool must pass session_id into request headers."""

    def test_call_tool_forwards_session_id(self):
        captured: list[httpx.Request] = []
        conn = _connector_with_capture(captured)

        conn.call_tool(
            "test_tool",
            {"query": "x"},
            principal={"username": "carol"},
            session_id="sess-xyz",
        )

        req = captured[0]
        assert req.headers.get("x-atria-session") == "sess-xyz"
        decoded = json.loads(req.headers.get("x-atria-principal", "{}"))
        assert decoded["username"] == "carol"


def test_broadcaster_wires_principal_onto_ctx():
    from atria.web.ws_tool_broadcaster import WebSocketToolBroadcaster
    from atria.core.skill_tools import SkillToolContext

    class _Reg:
        skill_ctx = SkillToolContext()

    reg = _Reg()
    WebSocketToolBroadcaster(reg, ws_manager=None, loop=None, session_id="s1",
                             principal={"username": "alice", "email": "a@x"})
    assert reg.skill_ctx.principal == {"username": "alice", "email": "a@x"}
    assert reg.skill_ctx.session_id == "s1"
