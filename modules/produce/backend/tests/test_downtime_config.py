"""E4 reason-code library (P-DOWN-06) + long-open alerts (P-DOWN-04)."""

from __future__ import annotations

import datetime as dt

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


def test_reason_library_scoped_to_line_and_machine():
    from domain.downtime import service

    service.add_reason(1, "Mechanical", "Jam", "M-01")
    service.add_reason(1, "Electrical", machine="press-3")
    service.add_reason(2, "Mechanical")

    lib = service.reason_library(1)
    assert len(lib) == 2  # only line 1
    # machine filter returns line-wide (machine null) + the specific machine
    press = service.reason_library(1, machine="press-3")
    assert {r["category"] for r in press} == {"Mechanical", "Electrical"}


def test_long_open_flags_downtime_over_threshold():
    from domain.downtime import service
    from domain.downtime.models import PrDowntime

    # Two open downtimes; backdate one 30 min via direct model insert.
    service.open_downtime(station_id=1, category="Mech")  # just now → under threshold
    with db.db_session() as s:
        old = PrDowntime(station_id=2, category="Mech", started_at=db.now() - dt.timedelta(minutes=30))
        s.add(old)

    alerts = service.long_open(threshold_minutes=15)
    assert len(alerts) == 1
    assert alerts[0]["station_id"] == 2
    assert alerts[0]["elapsed_minutes"] >= 15
