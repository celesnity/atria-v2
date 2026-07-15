"""E1 Giao việc & hàng đợi — logic thuần trên DB.

MVP: hàng đợi operator theo ưu tiên (P-WORK-01), nhận task (P-WORK-02),
gán/gán lại bởi tổ trưởng (P-WORK-04), board trạng thái tổ (P-WORK-05).
"""

from __future__ import annotations

from sqlalchemy import select

from db import db_session

from .models import TASK_STATES, PrShift, PrTask


class WorkError(Exception):
    """Vi phạm luật nghiệp vụ E1 (trạng thái sai, task không tồn tại...)."""


# --- Shift ----------------------------------------------------------------------
def create_shift(line_id: int, name: str, supervisor_id: str | None = None) -> dict:
    with db_session() as s:
        sh = PrShift(line_id=line_id, name=name, supervisor_id=supervisor_id)
        s.add(sh)
        s.flush()
        return sh.as_dict()


# --- Task -----------------------------------------------------------------------
def create_task(
    line_id: int,
    *,
    shift_id: int | None = None,
    station_id: int | None = None,
    operation_id: int | None = None,
    part_id: int | None = None,
    priority: int = 100,
) -> dict:
    with db_session() as s:
        t = PrTask(
            line_id=line_id,
            shift_id=shift_id,
            station_id=station_id,
            operation_id=operation_id,
            part_id=part_id,
            priority=priority,
        )
        s.add(t)
        s.flush()
        return t.as_dict()


def operator_queue(assignee_id: str) -> list[dict]:
    """Hàng đợi của một operator, ưu tiên cao trước (P-WORK-01).

    Gồm task đã gán cho họ mà chưa xong.
    """
    with db_session() as s:
        stmt = (
            select(PrTask)
            .where(PrTask.assignee_id == assignee_id, PrTask.status != "done")
            .order_by(PrTask.priority, PrTask.id)
        )
        return [r.as_dict() for r in s.scalars(stmt).all()]


def team_board(line_id: int, shift_id: int | None = None) -> list[dict]:
    """Mọi task của tổ/line trong một màn hình (P-WORK-05)."""
    with db_session() as s:
        stmt = select(PrTask).where(PrTask.line_id == line_id)
        if shift_id is not None:
            stmt = stmt.where(PrTask.shift_id == shift_id)
        stmt = stmt.order_by(PrTask.priority, PrTask.id)
        return [r.as_dict() for r in s.scalars(stmt).all()]


def _get(s, task_id: int) -> PrTask:
    t = s.get(PrTask, task_id)
    if t is None:
        raise WorkError(f"task {task_id} không tồn tại")
    return t


def assign_task(task_id: int, assignee_id: str) -> dict:
    """Tổ trưởng gán hoặc gán lại task (P-WORK-04)."""
    with db_session() as s:
        t = _get(s, task_id)
        if t.status in ("in_progress", "done"):
            raise WorkError(f"không gán lại task đang ở trạng thái {t.status!r}")
        t.assignee_id = assignee_id
        t.status = "assigned"
        s.flush()
        return t.as_dict()


def claim_task(task_id: int, assignee_id: str) -> dict:
    """Operator nhận task và đánh dấu đang làm (P-WORK-02)."""
    with db_session() as s:
        t = _get(s, task_id)
        if t.assignee_id not in (None, assignee_id):
            raise WorkError("task đã được gán cho người khác")
        t.assignee_id = assignee_id
        t.status = "in_progress"
        s.flush()
        return t.as_dict()


def set_status(task_id: int, status: str) -> dict:
    if status not in TASK_STATES:
        raise WorkError(f"status {status!r} không hợp lệ")
    with db_session() as s:
        t = _get(s, task_id)
        t.status = status
        s.flush()
        return t.as_dict()
