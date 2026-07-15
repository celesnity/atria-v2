"""Track B Read surface (R01-R07). Typed, read-only queries over Track A services."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent.connector import conn
from domain.downtime import service as downtime_service
from domain.exception import service as exception_service
from domain.handover import service as handover_service
from domain.oee import service as oee_service
from domain.sop import service as sop_service
from domain.wip import service as wip_service
from domain.work import service as work_service


class QueueQuery(BaseModel):
    assignee_id: str = Field(description="Operator id whose queue to read.")


@conn.read("read_queue", description="R01 — operator queue by priority.", params_model=QueueQuery,
           when_to_use="To see what an operator should work on next.")
def read_queue(assignee_id: str):
    return {"output": work_service.operator_queue(assignee_id)}


class LineQuery(BaseModel):
    line_id: int


@conn.read("read_wip", description="R02 — WIP per station for a line.", params_model=LineQuery,
           when_to_use="To find bottlenecks / WIP build-up on a line.")
def read_wip(line_id: int):
    return {"output": {"by_station": wip_service.wip_by_station()}}


class ShiftQuery(BaseModel):
    shift_id: int
    total_count: int = 0


@conn.read("read_oee", description="R03 — shift OEE + three losses.", params_model=ShiftQuery,
           when_to_use="To check whether the shift is on plan (OEE vs target).")
def read_oee(shift_id: int, total_count: int = 0):
    try:
        return {"output": oee_service.shift_oee(shift_id, total_count)}
    except oee_service.OeeError as exc:
        return {"output": {"error": str(exc)}}


@conn.read("read_downtime", description="R04 — open downtime + reason library.", params_model=LineQuery,
           when_to_use="To see current stoppages and the valid reason codes.")
def read_downtime(line_id: int):
    return {"output": {"open": downtime_service.open_downtimes(),
                       "reasons": downtime_service.reason_library(line_id)}}


class SopQuery(BaseModel):
    sop_id: int


@conn.read("read_sop", description="R05 — released SOP + steps for an operation.", params_model=SopQuery,
           when_to_use="To read the current approved work instruction.")
def read_sop(sop_id: int):
    return {"output": sop_service.released_version(sop_id)}


@conn.read("read_exceptions", description="R06 — open + escalated exceptions.", params_model=LineQuery,
           when_to_use="To see blocked jobs and what has been escalated.")
def read_exceptions(line_id: int):
    return {"output": {"open": exception_service.open_exceptions(line_id),
                       "escalated": exception_service.escalated_exceptions()}}


class HandoverQuery(BaseModel):
    from_shift_id: int


@conn.read("read_handover", description="R07 — shift handover + carry-forward.", params_model=HandoverQuery,
           when_to_use="To read the outgoing shift's handover before starting.")
def read_handover(from_shift_id: int):
    return {"output": handover_service.read_handover(from_shift_id)}
