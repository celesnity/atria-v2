"""E4 Downtime & andon tests — in-memory SQLite."""

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


def test_downtime_open_close_auto_timestamps():
    from domain.downtime import service

    dt_ = service.open_downtime(station_id=1, category="Mechanical", subcategory="Jam", code="M-01")
    assert dt_["started_at"] is not None and dt_["ended_at"] is None
    assert service.open_downtimes(station_id=1)

    closed = service.close_downtime(dt_["id"])
    assert closed["ended_at"] is not None
    assert service.open_downtimes(station_id=1) == []

    with pytest.raises(service.DowntimeError):
        service.close_downtime(dt_["id"])


def test_team_andon_visibility_and_resolve():
    from domain.downtime import service

    a1 = service.raise_andon(line_id=5, station_id=1, operator_id="op1", reason="kẹt phôi")
    service.raise_andon(line_id=5, station_id=2)
    service.raise_andon(line_id=9, station_id=3)  # line khác

    assert len(service.team_andons(5)) == 2  # chỉ line 5
    service.set_andon_status(a1["id"], "resolved")
    assert len(service.team_andons(5)) == 1  # resolved bị loại khỏi open

    with pytest.raises(service.DowntimeError):
        service.set_andon_status(a1["id"], "bogus")
