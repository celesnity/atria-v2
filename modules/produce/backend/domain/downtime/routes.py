"""E4 Downtime & andon — REST routes human-facing.

Operator: ghi downtime (P-DOWN-01), gọi andon (P-DOWN-02).
Tổ trưởng: xem andon toàn tổ (P-DOWN-05).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import service

router = APIRouter(prefix="/downtime", tags=["downtime"])


class DowntimeIn(BaseModel):
    station_id: int
    category: str = Field(min_length=1, max_length=64)
    subcategory: str | None = None
    code: str | None = None
    shift_id: int | None = None


class AndonIn(BaseModel):
    line_id: int
    station_id: int
    operator_id: str | None = None
    reason: str | None = None


class AndonStatusIn(BaseModel):
    status: str


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.DowntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/events")
def post_downtime(body: DowntimeIn) -> dict:
    return service.open_downtime(
        body.station_id, body.category, body.subcategory, body.code, body.shift_id
    )


@router.post("/events/{downtime_id}/close")
def post_close(downtime_id: int) -> dict:
    return _guard(service.close_downtime, downtime_id)


@router.get("/events/open")
def get_open(station_id: int | None = None) -> list[dict]:
    return service.open_downtimes(station_id)


@router.get("/alerts")
def get_alerts(threshold_minutes: float) -> list[dict]:
    """Downtime đang mở vượt ngưỡng thời gian (P-DOWN-04)."""
    return service.long_open(threshold_minutes)


class ReasonIn(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    subcategory: str | None = None
    code: str | None = None
    machine: str | None = None


@router.get("/lines/{line_id}/reasons")
def get_reasons(line_id: int, machine: str | None = None) -> list[dict]:
    return service.reason_library(line_id, machine)


@router.post("/lines/{line_id}/reasons")
def post_reason(line_id: int, body: ReasonIn) -> dict:
    """FDE/Admin cấu hình thư viện mã lý do downtime (P-DOWN-06)."""
    return service.add_reason(line_id, body.category, body.subcategory, body.code, body.machine)


@router.post("/andon")
def post_andon(body: AndonIn) -> dict:
    return service.raise_andon(body.line_id, body.station_id, body.operator_id, body.reason)


@router.post("/andon/{andon_id}/status")
def post_andon_status(andon_id: int, body: AndonStatusIn) -> dict:
    return _guard(service.set_andon_status, andon_id, body.status)


@router.get("/andon/line/{line_id}")
def get_team_andons(line_id: int, open_only: bool = True) -> list[dict]:
    return service.team_andons(line_id, open_only)
