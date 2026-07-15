"""send_message must not kill the agent turn when no channel is configured —
it redirects the agent to reply in-conversation instead (so it stays interactive)."""
from __future__ import annotations

from minder.core.context_engineering.tools.implementations import message_tool
from minder.core.context_engineering.tools.implementations.message_tool import MessageTool


def test_unconfigured_channel_soft_redirects_instead_of_failing(monkeypatch):
    # no channels configured at all
    monkeypatch.setattr(message_tool, "_load_channel_config", lambda: {})
    out = MessageTool().execute(channel="slack", message="please confirm")
    assert out["success"] is True          # turn is NOT aborted
    assert out["delivered"] is False
    assert "do NOT retry send_message" in out["output"]
    assert "in this conversation" in out["_llm_suffix"]


def test_missing_message_still_errors(monkeypatch):
    monkeypatch.setattr(message_tool, "_load_channel_config", lambda: {})
    out = MessageTool().execute(channel="slack", message="")
    assert out["success"] is False and "message is required" in out["error"]


def test_configured_channel_attempts_delivery(monkeypatch):
    # a configured (but unreachable) webhook is a real outage → still a failure,
    # not the soft redirect, so genuine misconfig/outage is visible.
    monkeypatch.setattr(
        message_tool, "_load_channel_config",
        lambda: {"webhook": {"webhook_url": "http://127.0.0.1:9/none"}},
    )
    out = MessageTool().execute(channel="webhook", message="hi")
    assert out["success"] is False
    assert out.get("delivered") is not True
