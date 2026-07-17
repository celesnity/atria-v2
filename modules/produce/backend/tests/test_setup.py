"""E7 Setup & changeover tests — in-memory SQLite."""

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


def test_changeover_blocks_complete_until_checklist_done():
    from domain.setup import service

    c = service.start_changeover(
        line_id=1,
        to_part_id=2,
        checklist=[{"name": "thay khuôn", "done": False}, {"name": "chỉnh cữ", "done": False}],
    )
    assert len(service.open_changeovers(1)) == 1
    with pytest.raises(service.SetupError):
        service.complete_changeover(c["id"])  # còn bước chưa done


def test_changeover_complete_and_first_piece():
    from domain.setup import service

    c = service.start_changeover(
        line_id=1, to_part_id=2, checklist=[{"name": "thay khuôn", "done": True}]
    )
    done = service.complete_changeover(c["id"])
    assert done["ended_at"] is not None
    assert service.open_changeovers(1) == []

    fp = service.record_first_piece(c["id"], passed=True, note="đạt")
    assert fp["passed"] is True

    with pytest.raises(service.SetupError):
        service.record_first_piece(9999, passed=True)
