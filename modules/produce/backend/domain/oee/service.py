"""E6 Cycle time & OEE — logic thuần.

Nạp production order làm chuẩn (P-OEE-02) rồi tính OEE ca hiện tại theo thời gian
thực (P-OEE-03): OEE = Availability × Performance × Quality.

- Availability = run_time / planned_time,  run_time = planned − downtime
- Performance  = (ideal_cycle_time × total_count) / run_time
- Quality      = good_count / total_count,  good = total − scrap

Downtime lấy qua E4, scrap qua E5 (gọi service, không đụng model epic khác).
`total_count` truyền vào (WIP counts ở skeleton chưa gắn shift_id).
"""

from __future__ import annotations

from sqlalchemy import select

from db import db_session

from domain.downtime import service as downtime_service
from domain.scrap import service as scrap_service

from .models import PrProductionOrder


class OeeError(Exception):
    """Vi phạm luật nghiệp vụ E6."""


def load_production_order(
    line_id: int,
    shift_id: int,
    ideal_cycle_time: float,
    target_count: int,
    planned_minutes: float,
    part_id: int | None = None,
) -> dict:
    """FDE/Admin nạp chuẩn cho ca (P-OEE-02)."""
    if ideal_cycle_time <= 0:
        raise OeeError("ideal_cycle_time phải > 0")
    with db_session() as s:
        po = PrProductionOrder(
            line_id=line_id,
            shift_id=shift_id,
            part_id=part_id,
            ideal_cycle_time=ideal_cycle_time,
            target_count=target_count,
            planned_minutes=planned_minutes,
        )
        s.add(po)
        s.flush()
        return po.as_dict()


def _production_order(shift_id: int) -> dict | None:
    with db_session() as s:
        po = s.scalars(
            select(PrProductionOrder)
            .where(PrProductionOrder.shift_id == shift_id)
            .order_by(PrProductionOrder.id.desc())
        ).first()
        return po.as_dict() if po else None


def compute_oee(planned_minutes, downtime_minutes, total_count, scrap_count, ideal_cycle_time):
    """Toán OEE thuần (không DB) — dễ test độc lập.

    Trả dict A/P/Q/oee (0..1). Biên: run_time ≤ 0 → tất cả 0; total_count 0 → P,Q=0.
    """
    planned = float(planned_minutes)
    run_time = planned - float(downtime_minutes)
    availability = (run_time / planned) if planned > 0 else 0.0
    availability = max(0.0, min(1.0, availability))

    run_seconds = max(0.0, run_time) * 60.0
    if total_count > 0 and run_seconds > 0:
        performance = (float(ideal_cycle_time) * total_count) / run_seconds
    else:
        performance = 0.0
    performance = max(0.0, min(1.0, performance))

    good = max(0, total_count - scrap_count)
    quality = (good / total_count) if total_count > 0 else 0.0

    return {
        "availability": round(availability, 4),
        "performance": round(performance, 4),
        "quality": round(quality, 4),
        "oee": round(availability * performance * quality, 4),
    }


def shift_oee(shift_id: int, total_count: int) -> dict:
    """OEE ca hiện tại (P-OEE-03): gom downtime (E4) + scrap (E5) + chuẩn (production order)."""
    po = _production_order(shift_id)
    if po is None:
        raise OeeError(f"chưa nạp production order cho ca {shift_id}")
    dt_min = downtime_service.downtime_minutes(shift_id)
    scrap = scrap_service.scrap_total(shift_id=shift_id)
    result = compute_oee(po["planned_minutes"], dt_min, total_count, scrap, po["ideal_cycle_time"])
    result |= {
        "shift_id": shift_id,
        "total_count": total_count,
        "scrap_count": scrap,
        "downtime_minutes": round(dt_min, 2),
        "target_count": po["target_count"],
    }
    return result
