"""E6 Cycle time & OEE — REST routes human-facing.

FDE/Admin: nạp production order (P-OEE-02).
Quản ca: OEE ca hiện tại vs target (P-OEE-03).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/oee", tags=["oee"])


class ProductionOrderIn(BaseModel):
    line_id: int
    shift_id: int
    ideal_cycle_time: float = Field(gt=0)
    target_count: int = Field(ge=0)
    planned_minutes: float = Field(ge=0)
    part_id: int | None = None


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.OeeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/production-orders")
def post_production_order(body: ProductionOrderIn) -> dict:
    return _guard(
        service.load_production_order,
        body.line_id,
        body.shift_id,
        body.ideal_cycle_time,
        body.target_count,
        body.planned_minutes,
        body.part_id,
    )


@router.get("/shifts/{shift_id}")
def get_shift_oee(shift_id: int, total_count: int = 0) -> dict:
    """OEE ca hiện tại (P-OEE-03). `total_count` = sản lượng ca tính tới hiện tại."""
    return _guard(service.shift_oee, shift_id, total_count)
