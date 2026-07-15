"""E8 Bàn giao ca — REST routes human-facing.

Tổ trưởng ca ra: tạo bàn giao (P-HAND-01). Ca vào: đọc & xác nhận (P-HAND-02).
Quản ca: carry-forward downtime bắc qua ca (P-HAND-03).
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/handover", tags=["handover"])


class HandoverIn(BaseModel):
    line_id: int
    from_shift_id: int
    to_shift_id: int | None = None
    output_count: int = 0
    pending: list[dict] = Field(default_factory=list)
    open_downtime: list[dict] = Field(default_factory=list)
    notes: str | None = None


class CarryForwardIn(BaseModel):
    downtime_id: int
    from_shift_id: int
    to_shift_id: int
    original_started_at: dt.datetime


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.HandoverError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/records")
def post_handover(body: HandoverIn) -> dict:
    return service.create_handover(
        body.line_id,
        body.from_shift_id,
        to_shift_id=body.to_shift_id,
        output_count=body.output_count,
        pending=body.pending,
        open_downtime=body.open_downtime,
        notes=body.notes,
    )


@router.get("/shifts/{from_shift_id}")
def get_handover(from_shift_id: int) -> dict | None:
    return service.read_handover(from_shift_id)


@router.post("/records/{handover_id}/acknowledge")
def post_ack(handover_id: int) -> dict:
    return _guard(service.acknowledge, handover_id)


@router.post("/carry-forward")
def post_carry_forward(body: CarryForwardIn) -> dict:
    return service.carry_forward(
        body.downtime_id, body.from_shift_id, body.to_shift_id, body.original_started_at
    )


@router.get("/shifts/{shift_id}/verify-standard")
def get_verify_standard(shift_id: int) -> dict:
    """Xác nhận chuẩn ca đã nạp đúng khi bắt đầu (P-HAND-04)."""
    return service.verify_standard(shift_id)
