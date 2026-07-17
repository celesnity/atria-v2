"""Track B Guidance surface (G01/G03). Declarative context + suggestion / decision
packets rendered into the UI; the person decides."""

from __future__ import annotations

from pydantic import BaseModel

from minder_python_sdk import assumption, card, decision_packet

from agent.connector import conn
from domain.exception import service as exception_service
from domain.sop import service as sop_service

conn.context.knowledge(
    "Produce is an MES. A licensed operator/supervisor stays in the loop for every "
    "dispatch decision. Never bypass poka-yoke or the risk gate."
)
conn.context.note("operator", "Operator screen: queue, e-SOP execution, WIP, downtime, scrap.")
conn.context.note("supervisor", "Supervisor screen: shift OEE, escalations, handover, holds.")


@conn.context.state("open_exceptions", "Currently open exceptions across lines 1-3.")
def _state_exceptions():
    out = []
    for line_id in (1, 2, 3):
        out.extend(exception_service.open_exceptions(line_id))
    return out


class NextStepArgs(BaseModel):
    job_id: int
    sop_id: int


@conn.tool(
    "guide_next_step",
    description="G01 — suggest the next step / correct setup for the operator.",
    params_model=NextStepArgs,
    risk="none",
    read_only=True,
    when_to_use="To nudge the operator toward the correct next SOP step.",
)
def guide_next_step(job_id: int, sop_id: int):
    released = sop_service.released_version(sop_id)
    done = {c["step_index"] for c in sop_service.job_progress(job_id)}
    steps = (released or {}).get("steps", [])
    nxt = next((i for i in range(len(steps)) if i not in done), None)
    msg = "Tất cả bước đã xong." if nxt is None else f"Bước tiếp theo: {steps[nxt].get('name')}"
    return {"output": msg, "card": card(msg, confidence=0.75)}


class DecisionArgs(BaseModel):
    line_id: int
    reason: str


@conn.tool(
    "guide_decision_packet",
    description="G03 — surface a decision packet for the supervisor to approve (blocks -> C03).",
    params_model=DecisionArgs,
    risk="medium",
    when_to_use="When a situation needs supervisor sign-off before a command runs.",
)
def guide_decision_packet(line_id: int, reason: str):
    return {
        "output": decision_packet(
            title=f"Escalate exception on line {line_id}?",
            action="cmd_raise_exception",
            arguments={"line_id": line_id, "reason": reason},
            assumptions=[assumption(f"'{reason}' warrants supervisor escalation.", 0.7)],
        )
    }
