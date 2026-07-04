"""Tests for the /api/transcribe endpoint (thin proxy to the ASR backend).

The ASR upstream is mocked (httpx), so these run with no sidecar and no model.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atria.web.dependencies.auth import require_authenticated_user
from atria.web.routes import transcribe as transcribe_module
from atria.web.routes.transcribe import router as transcribe_router


class _FakeResp:
    def __init__(self, status_code: int = 200, json_data: dict | None = None) -> None:
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://asr/v1/audio/transcriptions")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("upstream error", request=request, response=response)


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient used as an async context manager."""

    _resp: _FakeResp = _FakeResp(200, {"text": ""})
    _raise: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, *args, **kwargs) -> _FakeResp:
        if type(self)._raise is not None:
            raise type(self)._raise
        return type(self)._resp


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(transcribe_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient._raise = None
    app = FastAPI()
    app.include_router(transcribe_router)
    # Bypass Keycloak auth for the unit test.
    app.dependency_overrides[require_authenticated_user] = lambda: {"id": 1, "username": "tester"}
    return TestClient(app)


def test_transcribe_returns_text(client):
    _FakeAsyncClient._resp = _FakeResp(200, {"text": "hydraulic system 32 low pressure caution"})
    r = client.post("/api/transcribe", files={"file": ("speech.webm", b"RIFFfake", "audio/webm")})
    assert r.status_code == 200
    assert r.json() == {"text": "hydraulic system 32 low pressure caution"}


def test_transcribe_rejects_empty_upload(client):
    r = client.post("/api/transcribe", files={"file": ("speech.webm", b"", "audio/webm")})
    assert r.status_code == 400


def test_transcribe_upstream_error_is_502(client):
    _FakeAsyncClient._resp = _FakeResp(500, {})
    r = client.post("/api/transcribe", files={"file": ("speech.webm", b"RIFFfake", "audio/webm")})
    assert r.status_code == 502


def test_transcribe_upstream_unreachable_is_502(client):
    _FakeAsyncClient._raise = httpx.ConnectError("connection refused")
    r = client.post("/api/transcribe", files={"file": ("speech.webm", b"RIFFfake", "audio/webm")})
    assert r.status_code == 502


def test_auth_dependency_is_enforced():
    """The router must carry the auth dependency (no anonymous transcription)."""
    deps = [d.dependency for d in transcribe_router.dependencies]
    assert require_authenticated_user in deps
