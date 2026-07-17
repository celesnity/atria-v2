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

from sqlalchemy import func, select

from db import db_session

from domain.downtime import service as downtime_service
from domain.scrap import service as scrap_service

from .models import PrProductionOrder, PrSpeedLoss


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


def production_order_for(shift_id: int) -> dict | None:
    """Bản production order hiện hành của ca (public — dùng cho bàn giao P-HAND-04)."""
    return _production_order(shift_id)


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


# --- Speed loss (P-OEE-05) ------------------------------------------------------
def record_speed_loss(
    seconds: float,
    *,
    shift_id: int | None = None,
    station_id: int | None = None,
    job_id: int | None = None,
    reason: str | None = None,
) -> dict:
    with db_session() as s:
        sl = PrSpeedLoss(
            seconds=seconds, shift_id=shift_id, station_id=station_id, job_id=job_id, reason=reason
        )
        s.add(sl)
        s.flush()
        return sl.as_dict()


def speed_loss_minutes(shift_id: int) -> float:
    with db_session() as s:
        secs = s.scalar(
            select(func.coalesce(func.sum(PrSpeedLoss.seconds), 0.0)).where(
                PrSpeedLoss.shift_id == shift_id
            )
        )
        return round(float(secs or 0.0) / 60.0, 2)


# --- Loss breakdown (P-OEE-04) --------------------------------------------------
def loss_breakdown(shift_id: int, total_count: int) -> dict:
    """Bóc tách ba tổn thất theo phút cho một ca (P-OEE-04): availability / performance / quality.

    availability_loss = downtime; performance_loss = A×(1−P)×planned;
    quality_loss = A×P×(1−Q)×planned. Đơn vị phút trên planned time.
    """
    base = shift_oee(shift_id, total_count)  # có A/P/Q + planned/downtime
    po = _production_order(shift_id)
    planned = float(po["planned_minutes"]) if po else 0.0
    a, p, q = base["availability"], base["performance"], base["quality"]
    availability_loss = round(base["downtime_minutes"], 2)
    performance_loss = round(a * (1 - p) * planned, 2)
    quality_loss = round(a * p * (1 - q) * planned, 2)
    return {
        "shift_id": shift_id,
        "planned_minutes": planned,
        "availability_loss_min": availability_loss,
        "performance_loss_min": performance_loss,
        "quality_loss_min": quality_loss,
        "speed_loss_min": speed_loss_minutes(shift_id),
        "oee": base["oee"],
    }
