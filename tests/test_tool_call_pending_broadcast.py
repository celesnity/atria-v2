"""The pending tool-call broadcast carries name + id and a pending flag."""

from minder.web.web_ui_callback import WebUICallback
from minder.web.protocol import WSMessageType


def _make_callback():
    cb = WebUICallback.__new__(WebUICallback)
    cb.session_id = "sess1"
    cb._sent = []
    cb._broadcast = lambda msg: cb._sent.append(msg)  # type: ignore[attr-defined]
    return cb


def test_on_tool_call_pending_broadcasts_pending_tool_call():
    cb = _make_callback()
    cb.on_tool_call_pending("read_file", "call_abc")

    assert len(cb._sent) == 1
    msg = cb._sent[0]
    assert msg["type"] == WSMessageType.TOOL_CALL
    data = msg["data"]
    assert data["tool_name"] == "read_file"
    assert data["tool_call_id"] == "call_abc"
    assert data["pending"] is True
    assert data["arguments"] == {}
    assert data["session_id"] == "sess1"


def test_wants_stream_tokens_enabled():
    # Regression guard: the web callback opts into streaming callbacks.
    assert WebUICallback.wants_stream_tokens is True
