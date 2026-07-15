"""E5 Phế phẩm, lỗi & rework — logic thuần trên DB.

Ghi phế phẩm kèm mã lý do (P-SCRAP-01), đánh dấu rework (P-SCRAP-02),
hold/release lot (P-SCRAP-05). Tổng phế phẩm dùng cho Quality trong OEE (E6).
"""

from __future__ import annotations

from sqlalchemy import func, select

from db import db_session, now

from .models import PrHold, PrRework, PrScrap


class ScrapError(Exception):
    """Vi phạm luật nghiệp vụ E5."""


# --- Scrap (P-SCRAP-01) ---------------------------------------------------------
def record_scrap(
    reason_code: str,
    qty: int,
    *,
    station_id: int | None = None,
    job_id: int | None = None,
    shift_id: int | None = None,
    photo_ref: str | None = None,
) -> dict:
    with db_session() as s:
        sc = PrScrap(
            reason_code=reason_code,
            qty=qty,
            station_id=station_id,
            job_id=job_id,
            shift_id=shift_id,
            photo_ref=photo_ref,
        )
        s.add(sc)
        s.flush()
        return sc.as_dict()


def scrap_total(shift_id: int | None = None, station_id: int | None = None) -> int:
    with db_session() as s:
        stmt = select(func.coalesce(func.sum(PrScrap.qty), 0))
        if shift_id is not None:
            stmt = stmt.where(PrScrap.shift_id == shift_id)
        if station_id is not None:
            stmt = stmt.where(PrScrap.station_id == station_id)
        return int(s.scalar(stmt) or 0)


# --- Rework (P-SCRAP-02) --------------------------------------------------------
def mark_rework(lot_code: str, reason: str | None = None, job_id: int | None = None) -> dict:
    with db_session() as s:
        rw = PrRework(lot_code=lot_code, reason=reason, job_id=job_id)
        s.add(rw)
        s.flush()
        return rw.as_dict()


# --- Hold (P-SCRAP-05) ----------------------------------------------------------
def hold_lot(lot_code: str, reason: str | None = None, held_by: str | None = None) -> dict:
    with db_session() as s:
        h = PrHold(lot_code=lot_code, reason=reason, held_by=held_by)
        s.add(h)
        s.flush()
        return h.as_dict()


def release_lot(hold_id: int) -> dict:
    with db_session() as s:
        h = s.get(PrHold, hold_id)
        if h is None:
            raise ScrapError(f"hold {hold_id} không tồn tại")
        if h.status == "released":
            raise ScrapError("lot đã được release")
        h.status = "released"
        h.released_at = now()
        s.flush()
        return h.as_dict()


def active_holds() -> list[dict]:
    with db_session() as s:
        stmt = select(PrHold).where(PrHold.status == "held").order_by(PrHold.held_at)
        return [r.as_dict() for r in s.scalars(stmt).all()]
