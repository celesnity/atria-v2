"""Track A writes emit the right kinds through the seam (E01/E02/E03/E05)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db
import events


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    seen = []
    events.subscribe(lambda k, p: seen.append((k, p)))
    yield seen
    events.clear()


def _kinds(seen):
    return [k for k, _ in seen]


def test_wip_and_sop_emissions(sqlite_engine):
    from domain.sop import service as sop
    from domain.wip import service as wip

    job = wip.start_job(task_id=1, station_id=1)
    wip.complete_job(job["id"])
    v = sop.add_draft_version(sop.create_sop("S1", "T")["id"], steps=[{"name": "a"}])
    sop.publish_version(v["id"])
    sop.confirm_step(job_id=job["id"], sop_version_id=v["id"], step_index=0)
    assert "job.started" in _kinds(sqlite_engine)
    assert "job.completed" in _kinds(sqlite_engine)
    assert "step.confirmed" in _kinds(sqlite_engine)


def test_downtime_and_exception_emissions(sqlite_engine):
    from domain.downtime import service as dt
    from domain.exception import service as exc

    d = dt.open_downtime(station_id=1, category="Mech")
    dt.close_downtime(d["id"])
    dt.raise_andon(line_id=1, station_id=1)
    exc.raise_exception(line_id=1, reason="máy hỏng")
    kinds = _kinds(sqlite_engine)
    assert {"downtime.opened", "downtime.closed", "andon.raised", "exception.raised"} <= set(kinds)
