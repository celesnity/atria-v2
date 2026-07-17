"""E1 Work tests — in-memory SQLite. Queue ordering, claim, assign guardrails."""

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


def _line():
    from domain.config import service as cfg

    return cfg.create_line("L1", "Line 1")["id"]


def test_queue_ordered_by_priority():
    from domain.work import service

    line = _line()
    service.create_task(line, priority=200)  # thấp
    hi = service.create_task(line, priority=10)  # cao
    service.assign_task(hi["id"], "op1")
    lo_id = service.create_task(line, priority=50)["id"]
    service.assign_task(lo_id, "op1")

    q = service.operator_queue("op1")
    assert [t["priority"] for t in q] == [10, 50]  # ưu tiên cao trước


def test_claim_and_reassign_guardrails():
    from domain.work import service

    line = _line()
    t = service.create_task(line)
    claimed = service.claim_task(t["id"], "op1")
    assert claimed["status"] == "in_progress"

    # không gán lại task đang làm
    with pytest.raises(service.WorkError):
        service.assign_task(t["id"], "op2")

    # người khác không claim được
    other = service.create_task(line)
    service.assign_task(other["id"], "op1")
    with pytest.raises(service.WorkError):
        service.claim_task(other["id"], "op2")


def test_team_board_lists_all_line_tasks():
    from domain.work import service

    line = _line()
    service.create_task(line, priority=1)
    service.create_task(line, priority=2)
    board = service.team_board(line)
    assert len(board) == 2
