"""Tests for the ASR sidecar's /v1/realtime streaming endpoint.

The model pipeline is mocked; timing constants are shrunk so partials arrive
fast. Runs with no torch/transformers/librosa (librosa import is lazy).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_APP_PATH = Path(__file__).resolve().parents[1] / "services" / "asr" / "app.py"


def _load_app_module():
    spec = importlib.util.spec_from_file_location("asr_app_under_test", _APP_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


asr_app = _load_app_module()


@pytest.fixture
def client(monkeypatch):
    # Fast cadence + tiny decode threshold so tests don't wait on real timing.
    monkeypatch.setattr(asr_app, "TICK_SEC", 0.05)
    monkeypatch.setattr(asr_app, "MIN_DECODE_SEC", 0.01)
    # Fake ASR: transcript reflects how much audio was decoded.
    monkeypatch.setattr(
        asr_app, "_get_pipe", lambda: (lambda inp: {"text": f"heard {len(inp['raw'])} samples"})
    )
    return TestClient(asr_app.app)


def _pcm(seconds: float) -> bytes:
    return b"\x01\x00" * int(asr_app.TARGET_SR * seconds)


def test_realtime_partials_then_final(client):
    with client.websocket_connect("/v1/realtime") as ws:
        ws.send_bytes(_pcm(0.5))
        first = ws.receive_json()  # blocks until the decode loop ticks
        assert first["type"] == "partial"
        assert first["text"].startswith("heard")
        ws.send_text(json.dumps({"type": "stop"}))
        # Drain any in-flight partials until the final arrives.
        msg = ws.receive_json()
        while msg["type"] == "partial":
            msg = ws.receive_json()
        assert msg["type"] == "final"
        assert msg["text"].startswith("heard")


def test_realtime_stop_without_audio_yields_empty_final(client):
    with client.websocket_connect("/v1/realtime") as ws:
        ws.send_text(json.dumps({"type": "stop"}))
        msg = ws.receive_json()
        while msg["type"] == "partial":
            msg = ws.receive_json()
        assert msg == {"type": "final", "text": ""}


def test_realtime_buffer_cap(client, monkeypatch):
    # Cap at 1s: sending 2s of audio must decode at most ~1s worth of samples.
    monkeypatch.setattr(asr_app, "MAX_UTTERANCE_SEC", 1.0)
    with client.websocket_connect("/v1/realtime") as ws:
        ws.send_bytes(_pcm(2.0))
        ws.send_text(json.dumps({"type": "stop"}))
        msg = ws.receive_json()
        while msg["type"] == "partial":
            msg = ws.receive_json()
        assert msg["type"] == "final"
        decoded_samples = int(msg["text"].split()[1])
        assert decoded_samples <= asr_app.TARGET_SR  # ≤ 1s of samples


def test_transcribe_pcm_empty_returns_empty():
    assert asr_app._transcribe_pcm(b"") == ""
    assert asr_app._join("", "") == ""
    assert asr_app._join("a", "b") == "a b"
