"""Streaming tool calls: agent-side SSE consumer + per-tool capability flag.

The ReAct loop stays request/response; the handler pumps progress/card events to
the UI mid-call and returns the ``final`` to the agent.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parent.parent / "minder_python_sdk"
if str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from minder.core.modules import remote  # noqa: E402
from minder.core.skill_tools import SkillToolContext  # noqa: E402


def test_run_stream_pumps_progress_and_returns_final():
    events: list[dict] = []
    ctx = SkillToolContext(broadcaster=events.append)

    class _Conn:
        name = "demo"

        def stream_tool(self, tool, args, timeout=300.0, **kwargs):
            yield {"event": "progress", "message": "retrieving", "pct": 30}
            yield {"event": "card", "card": {"answer": "partial"}, "card_type": "demo_answer"}
            yield {"event": "final", "success": True, "output": "done",
                   "card": {"answer": "done"}, "card_type": "demo_answer"}

    out = remote._run_stream(ctx, _Conn(), "demo_stream", {}, "q")
    assert out["success"] is True and out["output"] == "done"
    types = [e["type"] for e in events]
    assert "module_progress" in types              # progress reached the UI live
    assert types.count("demo_answer") == 2         # intermediate + final card


def test_run_stream_connector_down_fails_closed():
    ctx = SkillToolContext(broadcaster=lambda e: None)

    class _Conn:
        name = "demo"

        def stream_tool(self, tool, args, timeout=300.0, **kwargs):
            raise remote.ConnectorUnreachable("down")
            yield  # unreachable; makes this a generator

    out = remote._run_stream(ctx, _Conn(), "t", {}, "q")
    assert out["output"]["validation_warnings"] == ["connector_unreachable:demo"]
    assert "unreachable" in out["_llm_suffix"].lower()


def test_make_handler_streaming_uses_stream_not_call():
    called: dict = {}
    ctx = SkillToolContext(broadcaster=lambda e: None)

    class _Conn:
        name = "demo"

        def stream_tool(self, tool, args, timeout=300.0, **kwargs):
            called["stream"] = True
            yield {"event": "final", "success": True, "output": "ok"}

        def call_tool(self, tool, args, timeout=110.0, **kwargs):
            called["call"] = True
            return {"success": True, "output": "x"}

    handler = remote._make_handler(ctx, _Conn(), "t", streaming=True)
    out = handler(query="q")
    assert called.get("stream") and "call" not in called
    assert out["output"] == "ok"


def _sdk_streaming_app():
    from minder_python_sdk import Connector, card

    conn = Connector("demo")

    @conn.tool("s", streaming=True, parameters={"type": "object", "properties": {}},
               card_type="demo_answer")
    def s(**kwargs):
        yield {"event": "progress", "pct": 10}
        yield {"event": "final", "success": True, "output": "done",
               "card": card("done"), "card_type": "demo_answer"}

    return conn.asgi()


def test_manifest_exposes_per_tool_streaming_flag():
    from fastapi.testclient import TestClient

    m = TestClient(_sdk_streaming_app()).get("/connector/manifest").json()
    tool = next(t for t in m["tools"] if t["name"] == "s")
    assert tool["streaming"] is True


def test_client_stream_tool_parses_sdk_sse():
    # RemoteConnector.stream_tool over the SDK's real SSE endpoint. TestClient is a
    # sync httpx.Client bound to the ASGI app, so the connector's .stream() works.
    from fastapi.testclient import TestClient

    rc = remote.RemoteConnector("demo", "http://testserver")
    rc._client = TestClient(_sdk_streaming_app())
    evts = list(rc.stream_tool("s", {}))
    assert [e["event"] for e in evts] == ["progress", "final"]
    assert evts[-1]["output"] == "done"
