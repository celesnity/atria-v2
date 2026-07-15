"""E5 Phế phẩm, lỗi & rework — REST routes human-facing.

Operator: ghi phế phẩm (P-SCRAP-01), đánh dấu rework (P-SCRAP-02).
Quản ca: hold/release lot (P-SCRAP-05).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/scrap", tags=["scrap"])


class ScrapIn(BaseModel):
    reason_code: str = Field(min_length=1, max_length=64)
    qty: int = Field(ge=1)
    station_id: int | None = None
    job_id: int | None = None
    shift_id: int | None = None
    photo_ref: str | None = None


class ReworkIn(BaseModel):
    lot_code: str = Field(min_length=1, max_length=128)
    reason: str | None = None
    job_id: int | None = None


class HoldIn(BaseModel):
    lot_code: str = Field(min_length=1, max_length=128)
    reason: str | None = None
    held_by: str | None = None


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.ScrapError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/records")
def post_scrap(body: ScrapIn) -> dict:
    return service.record_scrap(
        body.reason_code,
        body.qty,
        station_id=body.station_id,
        job_id=body.job_id,
        shift_id=body.shift_id,
        photo_ref=body.photo_ref,
    )


@router.get("/total")
def get_total(shift_id: int | None = None, station_id: int | None = None) -> dict:
    return {"total": service.scrap_total(shift_id, station_id)}


@router.get("/by-station")
def get_by_station(shift_id: int | None = None) -> list[dict]:
    """Phế phẩm theo station (P-SCRAP-04)."""
    return service.scrap_by_station(shift_id)


@router.post("/rework")
def post_rework(body: ReworkIn) -> dict:
    return service.mark_rework(body.lot_code, body.reason, body.job_id)


@router.post("/holds")
def post_hold(body: HoldIn) -> dict:
    return service.hold_lot(body.lot_code, body.reason, body.held_by)


@router.post("/holds/{hold_id}/release")
def post_release(hold_id: int) -> dict:
    return _guard(service.release_lot, hold_id)


@router.get("/holds/active")
def get_active_holds() -> list[dict]:
    return service.active_holds()
