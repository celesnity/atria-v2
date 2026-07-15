"""Smoke test: app import + health route."""

from fastapi.testclient import TestClient

import app


def test_health() -> None:
    c = TestClient(app.app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["module"] == "produce"
