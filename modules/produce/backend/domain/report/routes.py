"""E10 Báo cáo & hiển thị — REST routes human-facing.

Tổ trưởng: dashboard live trạng thái tổ (P-RPT-01).
Quản ca: báo cáo cuối ca tự tổng hợp (P-RPT-02).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import service

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/live/{line_id}")
def get_live(line_id: int) -> dict:
    """Dashboard live trạng thái tổ (P-RPT-01)."""
    return service.live_dashboard(line_id)


@router.get("/end-of-shift")
def get_end_of_shift(line_id: int, shift_id: int, total_count: int = 0) -> dict:
    """Báo cáo cuối ca (P-RPT-02). `total_count` = sản lượng ca."""
    return service.end_of_shift_report(line_id, shift_id, total_count)


@router.get("/why-late/{line_id}")
def get_why_late(line_id: int, shift_id: int, downtime_threshold_min: float = 15.0) -> dict:
    """Vì sao line X trễ — lần theo downtime/ngoại lệ/WIP (P-RPT-04)."""
    return service.why_late(line_id, shift_id, downtime_threshold_min)


class TrendIn(BaseModel):
    entries: list[dict]


@router.post("/trend")
def post_trend(body: TrendIn) -> list[dict]:
    """Xu hướng OEE qua các ca (P-RPT-03)."""
    return service.trend(body.entries)
