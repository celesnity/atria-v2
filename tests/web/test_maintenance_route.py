"""Tests for the /api/maintenance/signoff endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atria.web.dependencies.auth import require_authenticated_user
from atria.web.routes.maintenance import router as maintenance_router


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Route the module audit log to a temp file so the test doesn't touch the repo.
    monkeypatch.setenv("MC_AUDIT_LOG", str(tmp_path / "audit.log.jsonl"))
    app = FastAPI()
    app.include_router(maintenance_router)
    app.dependency_overrides[require_authenticated_user] = lambda: {"username": "alice", "id": 7}
    return TestClient(app), tmp_path / "audit.log.jsonl"


def test_signoff_records_event(client):
    tc, log_path = client
    r = tc.post(
        "/api/maintenance/signoff",
        json={"query": "brake temp MEL", "answer_summary": "Use MEL 32-42", "decision": "acknowledged"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["event"]["type"] == "signoff"
    assert body["event"]["engineer"] == "alice"
    assert body["event"]["decision"] == "acknowledged"
    assert "ts" in body["event"]  # stamped by audit.append_event

    # The event was persisted to the audit trail.
    lines = [json.loads(x) for x in log_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert any(e["type"] == "signoff" and e["engineer"] == "alice" for e in lines)


def test_signoff_auth_dependency_enforced():
    deps = [d.dependency for d in maintenance_router.dependencies]
    assert require_authenticated_user in deps
