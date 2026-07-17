"""E8 Handover tests — in-memory SQLite."""

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


def test_handover_create_read_acknowledge():
    from domain.handover import service

    h = service.create_handover(
        line_id=1,
        from_shift_id=1,
        output_count=320,
        pending=[{"task_id": 5, "note": "chờ vật tư"}],
        notes="line ổn",
    )
    assert h["acknowledged_at"] is None
    fetched = service.read_handover(from_shift_id=1)
    assert fetched["output_count"] == 320
    assert fetched["pending"][0]["task_id"] == 5

    acked = service.acknowledge(h["id"])
    assert acked["acknowledged_at"] is not None

    with pytest.raises(service.HandoverError):
        service.acknowledge(9999)


def test_carry_forward_keeps_original_timestamp():
    from domain.handover import service

    orig = dt.datetime(2026, 7, 15, 5, 30, tzinfo=dt.timezone.utc)
    cf = service.carry_forward(
        downtime_id=1, from_shift_id=1, to_shift_id=2, original_started_at=orig
    )
    assert cf["original_started_at"].startswith("2026-07-15T05:30")
