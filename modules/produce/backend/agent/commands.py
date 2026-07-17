"""Track B Command surface (C03/C07/C09). Low-risk, reversible, gated writes over
Track A services. Each carries an assumption ledger + an undo note."""

from __future__ import annotations

from pydantic import BaseModel, Field

from minder_python_sdk import assumption, card

from agent.connector import conn
from domain.exception import service as exception_service
from domain.handover import service as handover_service
from domain.report import service as report_service
from domain.wip import service as wip_service


class RaiseExceptionArgs(BaseModel):
    line_id: int
    reason: str = Field(description="Why the job is blocked (missing material, machine down, QC wait).")
    task_id: int | None = None
    job_id: int | None = None


@conn.tool(
    "cmd_raise_exception",
    description="C03 — create an exception from a detected block and escalate to the supervisor.",
    params_model=RaiseExceptionArgs,
    risk="low",
    reversible=True,
    undo="Resolve the exception via exception.resolve(id).",
    when_to_use="When an event indicates a blocked job that a supervisor should see.",
)
def cmd_raise_exception(line_id: int, reason: str, task_id: int | None = None, job_id: int | None = None):
    exc = exception_service.raise_exception(line_id, reason, task_id=task_id, job_id=job_id, raised_by="minder")
    escalated = exception_service.escalate(exc["id"])
    return {
        "output": escalated,
        "card": card(f"Raised + escalated exception {escalated['id']}.", confidence=0.9),
        "assumptions": [assumption("The detected block is real and needs supervisor attention.", 0.8)],
    }


class DraftHandoverArgs(BaseModel):
    line_id: int
    from_shift_id: int
    total_count: int = 0


@conn.tool(
    "cmd_draft_handover",
    description="C07 — build an auto-summarized end-of-shift handover draft.",
    params_model=DraftHandoverArgs,
    risk="low",
    reversible=True,
    undo="Delete the draft handover row.",
    when_to_use="At shift end, to pre-fill the handover from live data.",
)
def cmd_draft_handover(line_id: int, from_shift_id: int, total_count: int = 0):
    report = report_service.end_of_shift_report(line_id, from_shift_id, total_count)
    h = handover_service.create_handover(
        line_id, from_shift_id, output_count=report["output_count"],
        notes=f"Auto-draft: scrap={report['scrap_count']}, oee={report['oee']}",
    )
    return {
        "output": h,
        "card": card(f"Drafted handover {h['id']} for shift {from_shift_id}.", confidence=0.85),
        "assumptions": [assumption("Live counts are complete enough to summarize the shift.", 0.7)],
    }


class UpdateProductionArgs(BaseModel):
    station_id: int
    qty: int | None = None
    status: str | None = None
    job_id: int | None = None


@conn.tool(
    "cmd_update_production",
    description="C09 — update a production record (count and/or station status).",
    params_model=UpdateProductionArgs,
    risk="low",
    reversible=True,
    undo="Record the inverse count / restore the prior station status.",
    when_to_use="To reconcile a production record from a trusted signal.",
)
def cmd_update_production(station_id: int, qty: int | None = None, status: str | None = None, job_id: int | None = None):
    out = {}
    if qty is not None:
        out["count"] = wip_service.record_count(station_id, qty, job_id)
    if status is not None:
        out["status"] = wip_service.set_station_status(station_id, status)
    return {
        "output": out,
        "card": card(f"Updated production record for station {station_id}.", confidence=0.8),
        "assumptions": [assumption("The source signal for this update is trustworthy.", 0.7)],
    }
