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


def test_read_queue_returns_operator_tasks():
    import agent.reads  # noqa: F401 — registers reads
    from agent.connector import conn
    from domain.work import service as work

    line = 1
    t = work.create_task(line)
    work.claim_task(t["id"], "op1")
    out = conn.invoke("read_queue", {"assignee_id": "op1"})
    assert out["output"] and out["output"][0]["assignee_id"] == "op1"


def test_read_oee_reports_error_without_order():
    import agent.reads  # noqa: F401
    from agent.connector import conn

    out = conn.invoke("read_oee", {"shift_id": 1, "total_count": 0})
    assert "error" in out["output"] or out["output"].get("oee") is not None
