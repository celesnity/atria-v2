"""E5 defect rate / scrap-by-station (P-SCRAP-04) + E6 loss breakdown & speed loss (P-OEE-04/05)."""

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


def test_scrap_by_station_and_defect_rate():
    from domain.scrap import service

    service.record_scrap("D-01", 6, station_id=1, shift_id=1)
    service.record_scrap("D-02", 2, station_id=2, shift_id=1)
    by = {r["station_id"]: r["scrap"] for r in service.scrap_by_station(shift_id=1)}
    assert by == {1: 6, 2: 2}
    assert service.defect_rate(6, 200) == 0.03
    assert service.defect_rate(1, 0) == 0.0


def test_speed_loss_accumulates():
    from domain.oee import service

    service.record_speed_loss(120, shift_id=1)  # 2 min
    service.record_speed_loss(60, shift_id=1)  # 1 min
    assert service.speed_loss_minutes(1) == 3.0


def test_loss_breakdown_splits_three_losses():
    from domain.downtime import service as dt
    from domain.oee import service
    from domain.scrap import service as sc

    service.load_production_order(
        line_id=1, shift_id=1, ideal_cycle_time=60, target_count=500, planned_minutes=480
    )
    sc.record_scrap("D-01", 8, shift_id=1)
    d = dt.open_downtime(station_id=1, category="Mech", shift_id=1)
    dt.close_downtime(d["id"])

    lb = service.loss_breakdown(shift_id=1, total_count=400)
    assert lb["planned_minutes"] == 480
    assert lb["availability_loss_min"] >= 0
    assert lb["performance_loss_min"] >= 0
    assert lb["quality_loss_min"] >= 0
    assert 0.0 <= lb["oee"] <= 1.0
