"""E4 Downtime & andon — logic thuần trên DB.

Mở/đóng downtime với timestamp tự động (P-DOWN-01/03), gọi & giải quyết andon
(P-DOWN-02), liệt kê andon đang mở của tổ (P-DOWN-05).
"""

from __future__ import annotations

from sqlalchemy import func, select

from db import db_session, now


from .models import ANDON_STATES, PrAndon, PrDowntime


class DowntimeError(Exception):
    """Vi phạm luật nghiệp vụ E4."""


# --- Downtime (P-DOWN-01, P-DOWN-03) --------------------------------------------
def open_downtime(
    station_id: int,
    category: str,
    subcategory: str | None = None,
    code: str | None = None,
    shift_id: int | None = None,
) -> dict:
    with db_session() as s:
        dt_ = PrDowntime(
            station_id=station_id,
            category=category,
            subcategory=subcategory,
            code=code,
            shift_id=shift_id,
        )
        s.add(dt_)
        s.flush()
        return dt_.as_dict()


def close_downtime(downtime_id: int) -> dict:
    with db_session() as s:
        dt_ = s.get(PrDowntime, downtime_id)
        if dt_ is None:
            raise DowntimeError(f"downtime {downtime_id} không tồn tại")
        if dt_.ended_at is not None:
            raise DowntimeError("downtime đã đóng")
        dt_.ended_at = now()
        s.flush()
        return dt_.as_dict()


def open_downtimes(station_id: int | None = None) -> list[dict]:
    with db_session() as s:
        stmt = select(PrDowntime).where(PrDowntime.ended_at.is_(None))
        if station_id is not None:
            stmt = stmt.where(PrDowntime.station_id == station_id)
        stmt = stmt.order_by(PrDowntime.started_at)
        return [r.as_dict() for r in s.scalars(stmt).all()]


# --- Andon (P-DOWN-02, P-DOWN-05) -----------------------------------------------
def raise_andon(
    line_id: int, station_id: int, operator_id: str | None = None, reason: str | None = None
) -> dict:
    with db_session() as s:
        a = PrAndon(
            line_id=line_id, station_id=station_id, operator_id=operator_id, reason=reason
        )
        s.add(a)
        s.flush()
        return a.as_dict()


def set_andon_status(andon_id: int, status: str) -> dict:
    if status not in ANDON_STATES:
        raise DowntimeError(f"andon status {status!r} không hợp lệ")
    with db_session() as s:
        a = s.get(PrAndon, andon_id)
        if a is None:
            raise DowntimeError(f"andon {andon_id} không tồn tại")
        a.status = status
        if status == "resolved":
            a.resolved_at = now()
        s.flush()
        return a.as_dict()


def team_andons(line_id: int, open_only: bool = True) -> list[dict]:
    """Tình trạng andon mọi station trong tổ (P-DOWN-05)."""
    with db_session() as s:
        stmt = select(PrAndon).where(PrAndon.line_id == line_id)
        if open_only:
            stmt = stmt.where(PrAndon.status != "resolved")
        stmt = stmt.order_by(PrAndon.raised_at)
        return [r.as_dict() for r in s.scalars(stmt).all()]


# --- Cross-epic helper: tổng phút downtime của một ca (dùng cho OEE / E6) --------
def downtime_minutes(shift_id: int) -> float:
    """Tổng thời lượng (phút) các downtime của ca. Sự kiện đang mở tính tới `now`."""
    total = 0.0
    with db_session() as s:
        stmt = select(PrDowntime).where(PrDowntime.shift_id == shift_id)
        for dt_ in s.scalars(stmt).all():
            end = dt_.ended_at or now()
            total += (end - dt_.started_at).total_seconds() / 60.0
    return total


def top_reasons(shift_id: int, limit: int = 5) -> list[dict]:
    """Top mã lý do downtime của ca theo số lần (dùng cho báo cáo cuối ca / E10)."""
    with db_session() as s:
        stmt = (
            select(PrDowntime.category, func.count().label("n"))
            .where(PrDowntime.shift_id == shift_id)
            .group_by(PrDowntime.category)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [{"category": cat, "count": int(n)} for cat, n in s.execute(stmt).all()]
