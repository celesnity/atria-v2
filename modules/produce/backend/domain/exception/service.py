"""E9 Ngoại lệ & escalate — logic thuần trên DB.

Operator raise job bị chặn (P-EXCP-01), tổ trưởng phân loại (P-EXCP-02),
escalate lên quản ca kèm thời gian mở (P-EXCP-03).
"""

from __future__ import annotations

from sqlalchemy import select

from db import db_session, now

from .models import PrException


class ExceptionError(Exception):
    """Vi phạm luật nghiệp vụ E9."""


def raise_exception(
    line_id: int,
    reason: str,
    *,
    task_id: int | None = None,
    job_id: int | None = None,
    raised_by: str | None = None,
) -> dict:
    with db_session() as s:
        e = PrException(
            line_id=line_id, reason=reason, task_id=task_id, job_id=job_id, raised_by=raised_by
        )
        s.add(e)
        s.flush()
        return e.as_dict()


def _get(s, exc_id: int) -> PrException:
    e = s.get(PrException, exc_id)
    if e is None:
        raise ExceptionError(f"exception {exc_id} không tồn tại")
    return e


def triage(exc_id: int, category: str) -> dict:
    """Tổ trưởng phân loại (P-EXCP-02)."""
    with db_session() as s:
        e = _get(s, exc_id)
        e.category = category
        if e.status == "open":
            e.status = "triaged"
        s.flush()
        return e.as_dict()


def escalate(exc_id: int) -> dict:
    with db_session() as s:
        e = _get(s, exc_id)
        e.status = "escalated"
        e.escalated_at = now()
        s.flush()
        return e.as_dict()


def resolve(exc_id: int) -> dict:
    with db_session() as s:
        e = _get(s, exc_id)
        e.status = "resolved"
        e.resolved_at = now()
        s.flush()
        return e.as_dict()


def open_exceptions(line_id: int) -> list[dict]:
    """Ngoại lệ đang mở của tổ (P-EXCP-02)."""
    with db_session() as s:
        stmt = (
            select(PrException)
            .where(PrException.line_id == line_id, PrException.status != "resolved")
            .order_by(PrException.opened_at)
        )
        return [r.as_dict() for r in s.scalars(stmt).all()]


def escalated_exceptions() -> list[dict]:
    """Quản ca xem cái đã escalate kèm thời gian mở (P-EXCP-03)."""
    with db_session() as s:
        stmt = (
            select(PrException)
            .where(PrException.status == "escalated")
            .order_by(PrException.opened_at)
        )
        return [r.as_dict() for r in s.scalars(stmt).all()]
