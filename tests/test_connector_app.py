"""Contract tests for the maintenance_copilot connector service.

These import the service module directly (not over HTTP) with the pipeline
mocked, so they run without qdrant/llm sidecars.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "modules/maintenance_copilot/backend"


def _load_service():
    """Import backend/service.py with its pipeline dir on sys.path."""
    sys.path.insert(0, str(BACKEND / "pipeline"))
    spec = importlib.util.spec_from_file_location("mc_service", BACKEND / "service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unavailable_payload_is_low_confidence_review_required():
    svc = _load_service()
    card = svc.unavailable_payload("why is the APU inop?", "qdrant")
    assert card["confidence"] == 0.0
    assert card["confidence_band"] == "low"
    assert card["review_required"] is True
    assert card["citations"] == []
    assert card["validation_warnings"] == ["service_unavailable:qdrant"]


def test_unavailable_suffix_names_service():
    svc = _load_service()
    assert "{service}" in svc.UNAVAILABLE_SUFFIX
    assert "Do NOT" in svc.UNAVAILABLE_SUFFIX


def _client(monkeypatch, run_query_impl):
    """Build a TestClient with service.run_query patched."""
    from fastapi.testclient import TestClient

    # Ensure backend is on sys.path so app.py can import service
    sys.path.insert(0, str(BACKEND))
    sys.path.insert(0, str(BACKEND / "pipeline"))
    spec = importlib.util.spec_from_file_location("mc_app", BACKEND / "app.py")
    app_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_mod)
    monkeypatch.setattr(app_mod.service, "run_query", run_query_impl)
    return TestClient(app_mod.app), app_mod


def test_health_ok(monkeypatch):
    client, _ = _client(monkeypatch, lambda *a, **k: {})
    r = client.get("/connector/health")
    assert r.status_code == 200
    assert r.json()["module"] == "maintenance_copilot"


def test_manifest_lists_the_query_tool(monkeypatch):
    client, _ = _client(monkeypatch, lambda *a, **k: {})
    body = client.get("/connector/manifest").json()
    names = [t["name"] for t in body["tools"]]
    assert "maintenance_copilot_query" in names
    assert body["remote"]["exposed"]["dashboard"] == "./Dashboard"


def test_tool_call_returns_card(monkeypatch):
    fake = {"answer": "Torque to 40 Nm.", "confidence": 0.9, "confidence_band": "high",
            "citations": [], "review_required": False}
    client, _ = _client(monkeypatch, lambda *a, **k: fake)
    r = client.post("/connector/tools/maintenance_copilot_query",
                    json={"arguments": {"query": "torque?"}})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["card"]["answer"] == "Torque to 40 Nm."
    assert body["llm_suffix"] is None


def test_tool_call_sidecar_down_returns_unavailable_card_and_suffix(monkeypatch):
    # Create the boom function that will raise the exception.
    # The exception class comes from app_mod.service, which is loaded inside _client.
    def boom(*a, **k):
        # Will be replaced after _client returns
        pass

    client, app_mod = _client(monkeypatch, boom)

    # Now define boom to use the app_mod's service exception class (so identity matches)
    def boom_real(*a, **k):
        raise app_mod.service.ServiceUnavailableError("qdrant")

    monkeypatch.setattr(app_mod.service, "run_query", boom_real)
    r = client.post("/connector/tools/maintenance_copilot_query",
                    json={"arguments": {"query": "torque?"}})
    body = r.json()
    assert body["success"] is True  # fail-closed but structured, not an error
    assert body["card"]["review_required"] is True
    assert "qdrant" in body["llm_suffix"]


def test_unknown_tool_is_404(monkeypatch):
    client, _ = _client(monkeypatch, lambda *a, **k: {})
    r = client.post("/connector/tools/nope", json={"arguments": {}})
    assert r.status_code == 404


def test_sidecar_health_endpoint(monkeypatch):
    client, app_mod = _client(monkeypatch, lambda **k: {})
    monkeypatch.setattr(app_mod.service, "sidecar_health",
                        lambda: {"qdrant": "ok", "llm": "error: down"})
    r = client.get("/connector/sidecar-health")
    assert r.status_code == 200
    assert r.json()["qdrant"] == "ok"


def test_signoff_endpoint_records_event(monkeypatch):
    client, app_mod = _client(monkeypatch, lambda **k: {})
    captured = {}
    def fake_record(payload):
        captured.update(payload)
        return {"id": "evt1", **payload}
    monkeypatch.setattr(app_mod.service, "record_signoff", fake_record)
    r = client.post("/connector/signoff", json={"engineer": "eng@x", "decision": "acknowledged"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert captured["engineer"] == "eng@x"
    assert captured["type"] == "signoff"
