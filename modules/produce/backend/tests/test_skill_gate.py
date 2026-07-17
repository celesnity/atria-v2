"""E1×E11 skill-gated assignment (P-WORK-03 / P-CFG-03) + shift-wide load (P-WORK-06)."""

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


def _setup_skilled_operation():
    from domain.config import service as cfg

    line = cfg.create_line("L1", "Line 1")["id"]
    skill = cfg.create_skill("WELD", "Welding")["id"]
    op = cfg.create_operation(line, "OP-W", "Weld", required_skill_id=skill)["id"]
    return line, skill, op


def test_claim_blocked_without_skill_then_allowed():
    from domain.config import service as cfg
    from domain.work import service as work

    line, skill, op = _setup_skilled_operation()
    task = work.create_task(line, operation_id=op)

    with pytest.raises(work.WorkError):
        work.claim_task(task["id"], "op1")  # chưa có kỹ năng

    cfg.grant_operator_skill("op1", skill)
    claimed = work.claim_task(task["id"], "op1")
    assert claimed["status"] == "in_progress"


def test_assign_blocked_without_skill():
    from domain.work import service as work

    line, _skill, op = _setup_skilled_operation()
    task = work.create_task(line, operation_id=op)
    with pytest.raises(work.WorkError):
        work.assign_task(task["id"], "op2")


def test_operation_without_skill_is_open():
    from domain.config import service as cfg
    from domain.work import service as work

    line = cfg.create_line("L2", "Line 2")["id"]
    op = cfg.create_operation(line, "OP-F", "Free")["id"]  # no required skill
    task = work.create_task(line, operation_id=op)
    assert work.claim_task(task["id"], "anyone")["status"] == "in_progress"


def test_shift_load_groups_by_line_and_status():
    from domain.work import service as work

    work.create_task(1, shift_id=7)
    t2 = work.create_task(1, shift_id=7)
    work.assign_task(t2["id"], "op1")
    work.create_task(2, shift_id=7)

    load = {row["line_id"]: row for row in work.shift_load(7)}
    assert load[1]["total"] == 2
    assert load[1]["queued"] == 1 and load[1]["assigned"] == 1
    assert load[2]["total"] == 1
