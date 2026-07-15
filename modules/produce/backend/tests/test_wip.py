"""E3 WIP tests — in-memory SQLite. Job lifecycle, counts, station status, lot scan."""

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


def _task():
    from domain.config import service as cfg
    from domain.work import service as work

    line = cfg.create_line("L1", "Line 1")["id"]
    return work.create_task(line)["id"]


def test_job_auto_timestamps():
    from domain.wip import service

    job = service.start_job(_task())
    assert job["started_at"] is not None and job["ended_at"] is None
    done = service.complete_job(job["id"])
    assert done["status"] == "done" and done["ended_at"] is not None

    # không complete lại
    with pytest.raises(service.WipError):
        service.complete_job(job["id"])


def test_counts_sum_per_station():
    from domain.wip import service

    service.record_count(station_id=7, qty=10)
    service.record_count(station_id=7, qty=5)
    service.record_count(station_id=8, qty=3)
    assert service.station_total(7) == 15
    assert service.station_total(8) == 3


def test_station_status_upsert_and_validation():
    from domain.wip import service

    service.set_station_status(1, "running")
    assert service.get_station_status(1)["status"] == "running"
    service.set_station_status(1, "down")
    assert service.get_station_status(1)["status"] == "down"
    with pytest.raises(service.WipError):
        service.set_station_status(1, "bogus")


def test_lot_scan_traceability():
    from domain.wip import service

    job = service.start_job(_task())
    service.scan_lot(job["id"], "LOT-123")
    service.scan_lot(job["id"], "MAT-999", kind="material")
    lots = service.job_lots(job["id"])
    assert {l["code"] for l in lots} == {"LOT-123", "MAT-999"}
