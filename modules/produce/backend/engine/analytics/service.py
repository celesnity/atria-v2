"""Live dashboard + period close, both derived from the event log & interrupts."""

from __future__ import annotations

from sqlalchemy.orm import Session

from engine.core import auth, eventlog as el
from engine.core.auth import Principal
from engine.core.eventlog import PrEvent
from engine.db import now
from engine.exception.models import PrInterrupt


def open_period(session: Session, scope_path: str) -> "PrPeriod":
    from engine.analytics.models import PrPeriod

    p = PrPeriod(scope_path=scope_path, opened_at=now())
    session.add(p)
    return p


def _under(column, scope_path: str):
    """SQL predicate: column path is scope_path or nested under it."""
    return (column == scope_path) | (column.like(scope_path + "/%"))


def live_dashboard(session: Session, scope_path: str, target: int = 0) -> dict:
    throughput = (
        session.query(PrEvent)
        .filter(PrEvent.type == el.WORK_ITEM_COMPLETED)
        .filter(_under(PrEvent.scope_path, scope_path))
        .count()
    )
    open_interrupts = (
        session.query(PrInterrupt)
        .filter(PrInterrupt.status == "open")
        .filter(_under(PrInterrupt.scope_path, scope_path))
        .count()
    )
    return {
        "scope_path": scope_path,
        "throughput": throughput,
        "target": target,
        "open_interrupts": open_interrupts,
    }


def close_period(
    session: Session, principal: Principal, period_id: int, target: int = 0
) -> "PrPeriod":
    from engine.analytics.models import PrPeriod

    p = session.get(PrPeriod, period_id)
    auth.require(principal, "close_period", p.scope_path)
    p.summary = live_dashboard(session, p.scope_path, target=target)
    p.closed_at = now()
    el.emit(
        session, type=el.PERIOD_CLOSED, scope_path=p.scope_path,
        actor_subject=principal.subject, payload={"period_id": p.id},
    )
    return p
