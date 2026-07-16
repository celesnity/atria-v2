"""Raise and resolve interrupts, auto-timed, event-logged."""

from __future__ import annotations

from sqlalchemy.orm import Session

from engine.core import auth, eventlog as el
from engine.core.auth import Principal
from engine.db import now
from engine.exception.models import PrInterrupt


def raise_interrupt(
    session: Session,
    principal: Principal,
    scope_path: str,
    reason_code_id: int,
    work_item_id: int | None = None,
    step_run_id: int | None = None,
) -> PrInterrupt:
    auth.require(principal, "raise_exception", scope_path)
    it = PrInterrupt(
        work_item_id=work_item_id, step_run_id=step_run_id, scope_path=scope_path,
        reason_code_id=reason_code_id, status="open", started_at=now(),
        raised_by=principal.subject,
    )
    session.add(it)
    session.flush()
    el.emit(
        session, type=el.INTERRUPT_RAISED, scope_path=scope_path,
        actor_subject=principal.subject, payload={"reason_code_id": reason_code_id},
        work_item_id=work_item_id, step_run_id=step_run_id,
    )
    return it


def resolve_interrupt(
    session: Session, principal: Principal, interrupt_id: int, disposition: str
) -> PrInterrupt:
    it = session.get(PrInterrupt, interrupt_id)
    auth.require(principal, "resolve_exception", it.scope_path)
    it.status = "resolved"
    it.resolved_at = now()
    it.disposition = disposition
    el.emit(
        session, type=el.INTERRUPT_RESOLVED, scope_path=it.scope_path,
        actor_subject=principal.subject, payload={"interrupt_id": it.id},
        work_item_id=it.work_item_id,
    )
    return it
