"""Smoke test: app import + health route."""

from fastapi.testclient import TestClient

import app


def test_health() -> None:
    c = TestClient(app.app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["module"] == "produce"


def test_cors_header_present():
    from fastapi.testclient import TestClient
    import app

    c = TestClient(app.app)
    r = c.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")
