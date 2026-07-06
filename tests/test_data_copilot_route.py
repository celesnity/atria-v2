"""Tests for the /api/data-copilot read/write route (resolver overridden)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch):
    from atria.web.routes import data_copilot as dc_route

    async def _fake_wd(session_id: str) -> str:
        return str(tmp_path)

    monkeypatch.setattr(dc_route, "_working_dir_for_session", _fake_wd)
    app = FastAPI()
    app.include_router(dc_route.router)
    return TestClient(app)


def test_write_then_read(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    w = client.put(
        "/api/data-copilot/write",
        json={
            "session_id": "s1",
            "file": "edited.csv",
            "columns": [{"name": "a"}, {"name": "b"}],
            "rows": [{"a": "1", "b": "x"}],
        },
    )
    assert w.status_code == 200 and w.json()["rows"] == 1
    r = client.get("/api/data-copilot/read", params={"session_id": "s1", "file": "edited.csv"})
    assert r.status_code == 200
    assert r.json()["rows"][0]["a"] == "1"


def test_read_missing_is_404(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    r = client.get("/api/data-copilot/read", params={"session_id": "s1", "file": "nope.csv"})
    assert r.status_code == 404


def test_report_endpoint_returns_markdown(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    run_dir = tmp_path / ".artifacts" / "data_copilot" / "s1" / "runs" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "report.md").write_text("# Report\n\nBody text.", encoding="utf-8")

    r = client.get("/api/data-copilot/report", params={"session_id": "s1", "run_dir": "runs/run1"})
    assert r.status_code == 200
    assert r.json()["report"] == "# Report\n\nBody text."


def test_report_endpoint_missing_is_404(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    r = client.get("/api/data-copilot/report", params={"session_id": "s1", "run_dir": "runs/run1"})
    assert r.status_code == 404
