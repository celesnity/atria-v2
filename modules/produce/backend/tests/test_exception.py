"""E9 Exception & escalate tests — in-memory SQLite."""

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


def test_exception_lifecycle():
    from domain.exception import service

    e = service.raise_exception(line_id=1, reason="thiếu vật tư", raised_by="op1")
    assert e["status"] == "open"
    assert len(service.open_exceptions(1)) == 1

    service.triage(e["id"], "material")
    esc = service.escalate(e["id"])
    assert esc["status"] == "escalated" and esc["escalated_at"] is not None
    assert len(service.escalated_exceptions()) == 1

    service.resolve(e["id"])
    assert service.open_exceptions(1) == []  # resolved rời khỏi danh sách mở


def test_guard_missing_exception():
    from domain.exception import service

    with pytest.raises(service.ExceptionError):
        service.escalate(4242)
