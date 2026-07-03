"""Tests for the /ws/transcribe streaming proxy (upstream sidecar mocked)."""

from __future__ import annotations

import asyncio
import json
import sys
import types

from fastapi import FastAPI
from fastapi.testclient import TestClient

from atria.web.transcribe_ws import _asr_realtime_url, transcribe_ws_endpoint


class FakeUpstream:
    """Stands in for the sidecar's /v1/realtime socket."""

    def __init__(self) -> None:
        self.sent: list = []
        self._q: asyncio.Queue = asyncio.Queue()

    async def send(self, data) -> None:
        self.sent.append(data)
        if isinstance(data, bytes):
            await self._q.put(json.dumps({"type": "partial", "text": "hydraulic"}))
        elif "stop" in data:
            await self._q.put(json.dumps({"type": "final", "text": "hydraulic system"}))
            await self._q.put(None)  # end of stream

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._q.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self) -> None:
        pass


def _client(monkeypatch, connect):
    fake_ws_module = types.SimpleNamespace(connect=connect)
    monkeypatch.setitem(sys.modules, "websockets", fake_ws_module)
    app = FastAPI()
    app.add_websocket_route("/ws/transcribe", transcribe_ws_endpoint)
    return TestClient(app)


def test_pipes_frames_up_and_transcripts_down(monkeypatch):
    upstream = FakeUpstream()

    async def connect(url, max_size=None):
        return upstream

    client = _client(monkeypatch, connect)
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_bytes(b"\x01\x00" * 4000)
        partial = ws.receive_json()
        assert partial == {"type": "partial", "text": "hydraulic"}
        ws.send_text(json.dumps({"type": "stop"}))
        final = ws.receive_json()
        assert final == {"type": "final", "text": "hydraulic system"}
    # Both the audio frame and the stop control reached the sidecar.
    assert any(isinstance(s, bytes) for s in upstream.sent)
    assert any(isinstance(s, str) and "stop" in s for s in upstream.sent)


def test_upstream_unreachable_sends_error(monkeypatch):
    async def connect(url, max_size=None):
        raise ConnectionRefusedError("sidecar down")

    client = _client(monkeypatch, connect)
    with client.websocket_connect("/ws/transcribe") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "unreachable" in msg["detail"]


def test_asr_realtime_url_derivation(monkeypatch):
    monkeypatch.setenv("ATRIA_ASR_BASE_URL", "http://asr:9000/v1")
    assert _asr_realtime_url() == "ws://asr:9000/v1/realtime"
    monkeypatch.setenv("ATRIA_ASR_BASE_URL", "https://managed.example.com/v1/")
    assert _asr_realtime_url() == "wss://managed.example.com/v1/realtime"
