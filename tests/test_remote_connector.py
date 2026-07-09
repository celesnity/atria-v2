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
