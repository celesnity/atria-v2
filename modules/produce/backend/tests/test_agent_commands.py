from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("minder_python_sdk")

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_c03_creates_and_escalates_exception():
    import agent.commands  # noqa: F401
    from agent.connector import conn
    from domain.exception import service as exc

    out = conn.invoke("cmd_raise_exception", {"line_id": 1, "reason": "thiếu vật tư"})
    assert out.get("output", {}).get("status") == "escalated"
    assert len(exc.escalated_exceptions()) == 1


def test_c09_updates_production_count():
    import agent.commands  # noqa: F401
    from agent.connector import conn
    from domain.wip import service as wip

    conn.invoke("cmd_update_production", {"station_id": 3, "qty": 10})
    assert wip.station_total(3) == 10
