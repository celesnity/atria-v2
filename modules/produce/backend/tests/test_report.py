"""E10 Report tests — cross-epic aggregation (in-memory SQLite)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_live_dashboard_aggregates_epics():
    from domain.downtime import service as dt
    from domain.exception import service as exc
    from domain.report import service
    from domain.work import service as work

    work.create_task(line_id=1)
    dt.raise_andon(line_id=1, station_id=1)
    exc.raise_exception(line_id=1, reason="máy hỏng")

    dash = service.live_dashboard(1)
    assert len(dash["tasks"]) == 1
    assert len(dash["open_andons"]) == 1
    assert len(dash["open_exceptions"]) == 1


def test_end_of_shift_report_without_production_order():
    from domain.downtime import service as dt
    from domain.report import service
    from domain.scrap import service as sc

    sc.record_scrap("D-01", 4, shift_id=1)
    d1 = dt.open_downtime(station_id=1, category="Mech", shift_id=1)
    dt.close_downtime(d1["id"])
    dt.open_downtime(station_id=2, category="Mech", shift_id=1)  # 2 x Mech

    rpt = service.end_of_shift_report(line_id=1, shift_id=1, total_count=300)
    assert rpt["output_count"] == 300
    assert rpt["scrap_count"] == 4
    assert rpt["oee"]["error"]  # chưa nạp production order → OEE báo lỗi mềm
    assert rpt["top_downtime_reasons"][0] == {"category": "Mech", "count": 2}
