"""The typed operational event log — a closed ontology owned by the engine."""

from __future__ import annotations

import jsonschema
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import Session
from sqlalchemy.types import JSON

from engine.db import Base, now

# --- Ontology (closed set) ---------------------------------------------------
WORK_ITEM_CLAIMED = "work_item.claimed"
WORK_ITEM_STARTED = "work_item.started"
WORK_ITEM_COMPLETED = "work_item.completed"
STEP_ENTERED = "step.entered"
STEP_OUTPUT_SUBMITTED = "step.output_submitted"
STEP_REJECTED = "step.rejected"
INTERRUPT_RAISED = "interrupt.raised"
INTERRUPT_RESOLVED = "interrupt.resolved"
ESCALATION_RAISED = "escalation.raised"
ESCALATION_ACKNOWLEDGED = "escalation.acknowledged"
RESOURCE_STATE_CHANGED = "resource.state_changed"
TRACE_SCANNED = "trace.scanned"
OUTPUT_DISPOSITION = "output.disposition"
PERIOD_CLOSED = "period.closed"
OVERRIDE_LOGGED = "override.logged"


def _obj(required: dict[str, str] | None = None) -> dict:
    """Small helper: an object schema with typed required keys."""
    required = required or {}
    return {
        "type": "object",
        "properties": {k: {"type": v} for k, v in required.items()},
        "required": list(required.keys()),
    }


PAYLOAD_SCHEMAS: dict[str, dict] = {
    WORK_ITEM_CLAIMED: _obj({"work_item_id": "integer"}),
    WORK_ITEM_STARTED: _obj({"work_item_id": "integer"}),
    WORK_ITEM_COMPLETED: _obj({"work_item_id": "integer"}),
    STEP_ENTERED: _obj({"step_run_id": "integer", "step_key": "string"}),
    STEP_OUTPUT_SUBMITTED: _obj({"step_run_id": "integer"}),
    STEP_REJECTED: _obj({"step_run_id": "integer", "error": "string"}),
    INTERRUPT_RAISED: _obj({"reason_code_id": "integer"}),
    INTERRUPT_RESOLVED: _obj({"interrupt_id": "integer"}),
    ESCALATION_RAISED: _obj({"escalation_id": "integer"}),
    ESCALATION_ACKNOWLEDGED: _obj({"escalation_id": "integer"}),
    RESOURCE_STATE_CHANGED: _obj({"state": "string"}),
    TRACE_SCANNED: _obj({"code": "string", "kind": "string"}),
    OUTPUT_DISPOSITION: _obj({"step_run_id": "integer", "disposition": "string"}),
    PERIOD_CLOSED: _obj({"period_id": "integer"}),
    OVERRIDE_LOGGED: _obj({"reason": "string"}),
}

ALL = frozenset(PAYLOAD_SCHEMAS.keys())


class PrEvent(Base):
    __tablename__ = "pr_event"

    seq = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False, index=True)
    scope_path = Column(String, nullable=False, index=True)
    work_item_id = Column(Integer, nullable=True, index=True)
    step_run_id = Column(Integer, nullable=True)
    actor_subject = Column(String, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    occurred_at = Column(DateTime(timezone=True), nullable=False)


def emit(
    session: Session,
    *,
    type: str,
    scope_path: str,
    actor_subject: str,
    payload: dict | None = None,
    work_item_id: int | None = None,
    step_run_id: int | None = None,
) -> PrEvent:
    if type not in PAYLOAD_SCHEMAS:
        raise ValueError(f"unknown event type: {type}")
    payload = payload or {}
    jsonschema.validate(payload, PAYLOAD_SCHEMAS[type])
    row = PrEvent(
        type=type,
        scope_path=scope_path,
        work_item_id=work_item_id,
        step_run_id=step_run_id,
        actor_subject=actor_subject,
        payload=payload,
        occurred_at=now(),
    )
    session.add(row)
    return row
