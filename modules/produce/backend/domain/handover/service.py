"""E8 Bàn giao ca — logic thuần trên DB.

Tạo bản bàn giao cuối ca (P-HAND-01), ca vào đọc & xác nhận (P-HAND-02), ghi
carry-forward cho downtime bắc qua ca giữ timestamp gốc (P-HAND-03).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from db import db_session, now

from domain.oee import service as oee_service

from .models import PrCarryForward, PrHandover


class HandoverError(Exception):
    """Vi phạm luật nghiệp vụ E8."""


def create_handover(
    line_id: int,
    from_shift_id: int,
    *,
    to_shift_id: int | None = None,
    output_count: int = 0,
    pending: list[dict] | None = None,
    open_downtime: list[dict] | None = None,
    notes: str | None = None,
) -> dict:
    with db_session() as s:
        h = PrHandover(
            line_id=line_id,
            from_shift_id=from_shift_id,
            to_shift_id=to_shift_id,
            output_count=output_count,
            pending=pending or [],
            open_downtime=open_downtime or [],
            notes=notes,
        )
        s.add(h)
        s.flush()
        return h.as_dict()


def read_handover(from_shift_id: int) -> dict | None:
    """Ca vào đọc bàn giao của ca ra (P-HAND-02)."""
    with db_session() as s:
        h = s.scalars(
            select(PrHandover)
            .where(PrHandover.from_shift_id == from_shift_id)
            .order_by(PrHandover.id.desc())
        ).first()
        return h.as_dict() if h else None


def acknowledge(handover_id: int) -> dict:
    with db_session() as s:
        h = s.get(PrHandover, handover_id)
        if h is None:
            raise HandoverError(f"handover {handover_id} không tồn tại")
        h.acknowledged_at = now()
        s.flush()
        return h.as_dict()


def verify_standard(shift_id: int) -> dict:
    """Xác nhận production order / ideal cycle time / target đã nạp đúng khi ca bắt đầu (P-HAND-04)."""
    po = oee_service.production_order_for(shift_id)
    if po is None:
        return {"shift_id": shift_id, "loaded": False, "issues": ["chưa nạp production order"]}
    issues = []
    if not po.get("ideal_cycle_time"):
        issues.append("thiếu ideal cycle time")
    if not po.get("target_count"):
        issues.append("target_count = 0")
    if not po.get("planned_minutes"):
        issues.append("planned_minutes = 0")
    return {"shift_id": shift_id, "loaded": True, "issues": issues, "production_order": po}


def carry_forward(
    downtime_id: int,
    from_shift_id: int,
    to_shift_id: int,
    original_started_at: dt.datetime,
) -> dict:
    """Ghi carry-forward giữ timestamp gốc — chống đếm hai lần (P-HAND-03)."""
    with db_session() as s:
        cf = PrCarryForward(
            downtime_id=downtime_id,
            from_shift_id=from_shift_id,
            to_shift_id=to_shift_id,
            original_started_at=original_started_at,
        )
        s.add(cf)
        s.flush()
        return cf.as_dict()
