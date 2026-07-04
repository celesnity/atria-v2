"""Tests for chart override persistence + send_table chart_id stamping."""

from __future__ import annotations

import types

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from atria.core.modules import data_copilot_paths as dcp  # noqa: E402
from atria.web.routes import charts as charts_route  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    async def _fake_wd(session_id: str) -> str:
        return str(tmp_path)

    monkeypatch.setattr(charts_route, "_working_dir_for_session", _fake_wd)

    app = FastAPI()
    app.include_router(charts_route.router)
    return TestClient(app), tmp_path


def test_overrides_put_then_get_round_trip(client):
    c, tmp_path = client

    # No file yet → empty map.
    r = c.get("/api/charts/overrides", params={"session_id": "1"})
    assert r.status_code == 200
    assert r.json() == {}

    ov = {"title": "Q4 Revenue", "chartType": "line", "seriesColors": {"revenue": "#0051B6"}}
    w = c.put("/api/charts/overrides", json={"session_id": "1", "chart_id": "abc123", "overrides": ov})
    assert w.status_code == 200
    assert w.json()["success"] is True

    got = c.get("/api/charts/overrides", params={"session_id": "1"}).json()
    assert got == {"abc123": ov}

    # A second chart merges without clobbering the first.
    c.put("/api/charts/overrides", json={"session_id": "1", "chart_id": "def456", "overrides": {"title": "X"}})
    got2 = c.get("/api/charts/overrides", params={"session_id": "1"}).json()
    assert set(got2.keys()) == {"abc123", "def456"}

    # Persisted under the session's data_copilot root.
    path = dcp.data_copilot_root("1", str(tmp_path)) / "chart_overrides.json"
    assert path.is_file()


def test_overrides_put_requires_chart_id(client):
    c, _ = client
    r = c.put("/api/charts/overrides", json={"session_id": "1", "chart_id": "", "overrides": {}})
    assert r.status_code == 422


def test_send_table_stamps_chart_id(tmp_path):
    from atria.core.context_engineering.tools.implementations.send_table_tool import (
        SendTableHandler,
    )

    # Write a CSV into the session's data_copilot data/ dir.
    session_id = "42"
    data_dir = dcp.data_copilot_root(session_id, str(tmp_path)) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "t.csv").write_text("region,sales\nN,100\nS,200\n", encoding="utf-8")

    captured: dict = {}

    class _UICallback:
        def on_data(self, payload):
            captured.update(payload)

    class _Session:
        id = session_id
        working_directory = str(tmp_path)

    class _SessionManager:
        async def get_current_session(self):
            return _Session()

    context = types.SimpleNamespace(
        ui_callback=_UICallback(),
        session_manager=_SessionManager(),
    )

    handler = SendTableHandler()
    result = handler.send({"file": "t.csv", "title": "Sales"}, context)

    assert result["success"] is True
    assert "chart_id" in result["data_payload"]
    assert result["data_payload"]["chart_id"]  # non-empty
    # The same id was broadcast to the UI.
    assert captured["chart_id"] == result["data_payload"]["chart_id"]
