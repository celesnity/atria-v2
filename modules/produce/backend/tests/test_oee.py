"""E6 OEE tests — pure math + shift roll-up (in-memory SQLite)."""

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


def test_compute_oee_textbook_case():
    from domain.oee import service

    # planned 480', downtime 60' → A = 420/480 = 0.875
    # ideal 60s/u, total 400 → run 420*60=25200s; perf = 60*400/25200 = 0.9524
    # scrap 8 → quality = 392/400 = 0.98
    r = service.compute_oee(480, 60, 400, 8, 60)
    assert r["availability"] == 0.875
    assert r["performance"] == 0.9524
    assert r["quality"] == 0.98
    assert r["oee"] == round(0.875 * 0.9524 * 0.98, 4)


def test_compute_oee_edges():
    from domain.oee import service

    assert service.compute_oee(0, 0, 0, 0, 60)["oee"] == 0.0  # no planned time
    # downtime >= planned → availability 0
    assert service.compute_oee(100, 200, 10, 0, 60)["availability"] == 0.0
    # performance capped at 1.0
    assert service.compute_oee(480, 0, 100000, 0, 60)["performance"] == 1.0


def test_shift_oee_rolls_up_downtime_and_scrap():
    from domain.downtime import service as dt
    from domain.oee import service
    from domain.scrap import service as sc

    service.load_production_order(
        line_id=1, shift_id=1, ideal_cycle_time=60, target_count=500, planned_minutes=480
    )
    sc.record_scrap("D-01", 8, shift_id=1)
    # downtime open + close handled via helper summation; use an explicit closed event
    d = dt.open_downtime(station_id=1, category="Mech", shift_id=1)
    dt.close_downtime(d["id"])

    r = service.shift_oee(shift_id=1, total_count=400)
    assert r["scrap_count"] == 8
    assert r["target_count"] == 500
    assert 0.0 <= r["oee"] <= 1.0

    with pytest.raises(service.OeeError):
        service.shift_oee(shift_id=999, total_count=10)  # chưa nạp production order
