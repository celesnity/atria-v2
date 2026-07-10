"""Tests for the service-principal artifact push ingress."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atria.web.dependencies.service_auth import require_service_principal
from atria.web.dependencies.services import get_artifact_service
from atria.web.routes.artifacts_remote import router


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

@dataclass
class _FakeSession:
    metadata: dict = field(default_factory=lambda: {"conversation_id": 3})


@dataclass
class _FakeSessionWithoutConv:
    metadata: dict = field(default_factory=dict)


class _FakeArtifactService:
    async def upload_artifact(self, *, file_content, filename, content_length,
                               scope, conversation_id, project_id):
        return {"artifact_id": 7}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(monkeypatch):
    """App with both auth and artifact-service dependencies overridden.
    Session manager is monkeypatched on the state singleton."""
    from atria.web import state as _state_mod

    class _FakeSM:
        async def get_session_by_id(self, session_id: str):
            if session_id == "sess-ok":
                return _FakeSession()
            if session_id == "sess-no-conv":
                return _FakeSessionWithoutConv()
            return None  # unknown

    # Patch get_state() to return an object with a session_manager
    _orig_get_state = _state_mod.get_state

    class _FakeState:
        session_manager = _FakeSM()

    monkeypatch.setattr(_state_mod, "get_state", lambda: _FakeState())

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_service_principal] = lambda: {
        "client_id": "atria-module", "roles": ["module-push"]
    }
    app.dependency_overrides[get_artifact_service] = lambda: _FakeArtifactService()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_push_artifact_success(app_client):
    content = b"hello artifact"
    r = app_client.post("/api/artifacts/remote/push", json={
        "session_id": "sess-ok",
        "filename": "report.pdf",
        "content_b64": base64.b64encode(content).decode(),
    })
    assert r.status_code == 200
    assert r.json() == {"artifact_id": 7}


def test_push_artifact_no_conversation_returns_404(app_client):
    content = b"data"
    r = app_client.post("/api/artifacts/remote/push", json={
        "session_id": "sess-no-conv",
        "filename": "report.pdf",
        "content_b64": base64.b64encode(content).decode(),
    })
    assert r.status_code == 404


def test_push_artifact_unknown_session_returns_404(app_client):
    r = app_client.post("/api/artifacts/remote/push", json={
        "session_id": "nonexistent",
        "filename": "report.pdf",
        "content_b64": base64.b64encode(b"x").decode(),
    })
    assert r.status_code == 404


def test_push_artifact_bad_base64_returns_400(app_client):
    r = app_client.post("/api/artifacts/remote/push", json={
        "session_id": "sess-ok",
        "filename": "report.pdf",
        "content_b64": "!!!not-valid-base64!!!",
    })
    assert r.status_code == 400
