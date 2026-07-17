"""E5 Scrap / rework / hold tests — in-memory SQLite."""

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


def test_scrap_total_by_shift():
    from domain.scrap import service

    service.record_scrap("D-01", 3, shift_id=1)
    service.record_scrap("D-02", 2, shift_id=1)
    service.record_scrap("D-01", 5, shift_id=2)
    assert service.scrap_total(shift_id=1) == 5
    assert service.scrap_total(shift_id=2) == 5


def test_hold_and_release_lifecycle():
    from domain.scrap import service

    h = service.hold_lot("LOT-1", reason="nghi lỗi", held_by="sup1")
    assert len(service.active_holds()) == 1
    service.release_lot(h["id"])
    assert service.active_holds() == []
    with pytest.raises(service.ScrapError):
        service.release_lot(h["id"])


def test_rework_marks_lot():
    from domain.scrap import service

    rw = service.mark_rework("LOT-9", reason="xước bề mặt")
    assert rw["lot_code"] == "LOT-9"
