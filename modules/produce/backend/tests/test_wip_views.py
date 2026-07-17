"""E3 lot progress (P-WIP-04) + WIP-per-station (P-WIP-05)."""

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


def test_lot_progress_traces_jobs_and_steps():
    from domain.wip import service

    j1 = service.start_job(task_id=1, station_id=1)
    service.scan_lot(j1["id"], "LOT-A")
    service.add_job_step(j1["id"], "s1")
    service.complete_job(j1["id"])

    j2 = service.start_job(task_id=2, station_id=2)
    service.scan_lot(j2["id"], "LOT-A")  # same lot moves to next station

    prog = service.lot_progress("LOT-A")
    assert prog["job_count"] == 2
    assert prog["done_count"] == 1
    assert prog["jobs"][0]["steps_recorded"] == 1


def test_wip_by_station_counts_running_jobs():
    from domain.wip import service

    service.start_job(task_id=1, station_id=1)
    service.start_job(task_id=2, station_id=1)
    j = service.start_job(task_id=3, station_id=2)
    service.complete_job(j["id"])  # station 2 no longer running

    wip = {row["station_id"]: row["wip"] for row in service.wip_by_station()}
    assert wip == {1: 2}
