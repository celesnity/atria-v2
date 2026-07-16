"""Execution engine: claim, ordered step runs, contract-validated output."""

from __future__ import annotations

import jsonschema
from sqlalchemy.orm import Session

from engine.config import contract
from engine.config.models import PrWorkflowVersion
from engine.core import auth, eventlog as el
from engine.core.auth import Principal
from engine.db import now
from engine.execution.models import PrStepRun, PrWorkItem


def _graph(session: Session, work_item: PrWorkItem) -> dict:
    return session.get(PrWorkflowVersion, work_item.workflow_version_id).graph


def create_work_item(
    session: Session, principal: Principal, workflow_version_id: int, scope_path: str, priority: int = 100
) -> PrWorkItem:
    auth.require(principal, "assign", scope_path)
    wi = PrWorkItem(
        workflow_version_id=workflow_version_id,
        scope_path=scope_path,
        priority=priority,
        status="queued",
        created_at=now(),
    )
    session.add(wi)
    return wi


def claim(session: Session, principal: Principal, work_item_id: int) -> PrWorkItem:
    wi = session.get(PrWorkItem, work_item_id)
    auth.require(principal, "claim", wi.scope_path)
    wi.claimed_by = principal.subject
    wi.status = "claimed"
    el.emit(
        session,
        type=el.WORK_ITEM_CLAIMED,
        scope_path=wi.scope_path,
        actor_subject=principal.subject,
        payload={"work_item_id": wi.id},
        work_item_id=wi.id,
    )
    return wi


def start_step(
    session: Session, principal: Principal, work_item_id: int, step_key: str
) -> PrStepRun:
    wi = session.get(PrWorkItem, work_item_id)
    auth.require(principal, "execute", wi.scope_path)
    graph = _graph(session, wi)
    step = contract.get_step(graph, step_key)

    # Enforce order: every step in `entry` must have a completed run.
    for required in step.get("entry", []):
        done = (
            session.query(PrStepRun)
            .filter_by(work_item_id=wi.id, step_key=required, status="completed")
            .count()
        )
        if not done:
            raise ValueError(f"step '{step_key}' blocked: '{required}' not completed")

    first = wi.status == "claimed"
    wi.status = "in_progress"
    wi.current_step_key = step_key
    run = PrStepRun(
        work_item_id=wi.id, step_key=step_key, status="active",
        started_at=now(), assignee=principal.subject,
    )
    session.add(run)
    session.flush()
    if first:
        el.emit(
            session, type=el.WORK_ITEM_STARTED, scope_path=wi.scope_path,
            actor_subject=principal.subject, payload={"work_item_id": wi.id},
            work_item_id=wi.id,
        )
    el.emit(
        session, type=el.STEP_ENTERED, scope_path=wi.scope_path,
        actor_subject=principal.subject,
        payload={"step_run_id": run.id, "step_key": step_key},
        work_item_id=wi.id, step_run_id=run.id,
    )
    return run


def submit_output(
    session: Session,
    principal: Principal,
    step_run_id: int,
    data: dict,
    override_reason: str | None = None,
) -> PrStepRun:
    run = session.get(PrStepRun, step_run_id)
    wi = session.get(PrWorkItem, run.work_item_id)
    auth.require(principal, "submit_output", wi.scope_path)
    graph = _graph(session, wi)
    step = contract.get_step(graph, run.step_key)

    try:
        contract.validate_output(step, data)
    except jsonschema.ValidationError as err:
        if override_reason is None:
            el.emit(
                session, type=el.STEP_REJECTED, scope_path=wi.scope_path,
                actor_subject=principal.subject,
                payload={"step_run_id": run.id, "error": err.message},
                work_item_id=wi.id, step_run_id=run.id,
            )
            session.flush()
            session.commit()  # ponytail: commit the rejection audit before the 422 rollback swallows it
            raise
        auth.require(principal, "override", wi.scope_path)
        run.overridden = True
        run.override_reason = override_reason
        el.emit(
            session, type=el.OVERRIDE_LOGGED, scope_path=wi.scope_path,
            actor_subject=principal.subject, payload={"reason": override_reason},
            work_item_id=wi.id, step_run_id=run.id,
        )

    run.output = data
    run.validated = not run.overridden
    run.status = "completed"
    run.completed_at = now()
    el.emit(
        session, type=el.STEP_OUTPUT_SUBMITTED, scope_path=wi.scope_path,
        actor_subject=principal.subject, payload={"step_run_id": run.id},
        work_item_id=wi.id, step_run_id=run.id,
    )

    if not contract.next_steps(graph, run.step_key):
        wi.status = "completed"
        wi.current_step_key = None
        el.emit(
            session, type=el.WORK_ITEM_COMPLETED, scope_path=wi.scope_path,
            actor_subject=principal.subject, payload={"work_item_id": wi.id},
            work_item_id=wi.id,
        )
    return run
