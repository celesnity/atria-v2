"""E9 Ngoại lệ & escalate — REST routes human-facing.

Operator: raise job bị chặn (P-EXCP-01). Tổ trưởng: phân loại/escalate
(P-EXCP-02). Quản ca: xem đã escalate (P-EXCP-03).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/exception", tags=["exception"])


class ExceptionIn(BaseModel):
    line_id: int
    reason: str = Field(min_length=1, max_length=255)
    task_id: int | None = None
    job_id: int | None = None
    raised_by: str | None = None


class TriageIn(BaseModel):
    category: str = Field(min_length=1, max_length=64)


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.ExceptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/exceptions")
def post_exception(body: ExceptionIn) -> dict:
    return service.raise_exception(
        body.line_id,
        body.reason,
        task_id=body.task_id,
        job_id=body.job_id,
        raised_by=body.raised_by,
    )


@router.get("/line/{line_id}/open")
def get_open(line_id: int) -> list[dict]:
    return service.open_exceptions(line_id)


@router.get("/escalated")
def get_escalated() -> list[dict]:
    return service.escalated_exceptions()


@router.post("/exceptions/{exc_id}/triage")
def post_triage(exc_id: int, body: TriageIn) -> dict:
    return _guard(service.triage, exc_id, body.category)


@router.post("/exceptions/{exc_id}/escalate")
def post_escalate(exc_id: int) -> dict:
    return _guard(service.escalate, exc_id)


@router.post("/exceptions/{exc_id}/resolve")
def post_resolve(exc_id: int) -> dict:
    return _guard(service.resolve, exc_id)


class MaterialRequestIn(BaseModel):
    station_id: int
    part_code: str | None = None
    qty: int = 0
    requested_by: str | None = None


@router.get("/material-requests")
def get_material_requests() -> list[dict]:
    return service.open_material_requests()


@router.post("/material-requests")
def post_material_request(body: MaterialRequestIn) -> dict:
    """Yêu cầu bổ sung vật tư (P-EXCP-04, giao với Move)."""
    return service.request_material(body.station_id, body.part_code, body.qty, body.requested_by)
