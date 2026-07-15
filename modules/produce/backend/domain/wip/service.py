"""E3 WIP & bước sản xuất — logic thuần trên DB.

Timestamp start/end tự động (P-WIP-01), ghi count (P-WIP-02), cập nhật station
status (P-WIP-03), quét lot vào job (P-WIP-06).
"""

from __future__ import annotations

from sqlalchemy import func, select

from db import db_session, now

from .models import (
    STATION_STATES,
    PrCount,
    PrJob,
    PrJobStep,
    PrLotLink,
    PrStationStatus,
)


class WipError(Exception):
    """Vi phạm luật nghiệp vụ E3."""


# --- Job (P-WIP-01) -------------------------------------------------------------
def start_job(task_id: int, station_id: int | None = None, operator_id: str | None = None) -> dict:
    """Bắt đầu job — started_at gán tự động."""
    with db_session() as s:
        job = PrJob(task_id=task_id, station_id=station_id, operator_id=operator_id)
        s.add(job)
        s.flush()
        return job.as_dict()


def complete_job(job_id: int) -> dict:
    """Kết thúc job — ended_at gán tự động."""
    with db_session() as s:
        job = s.get(PrJob, job_id)
        if job is None:
            raise WipError(f"job {job_id} không tồn tại")
        if job.status != "running":
            raise WipError(f"job đang ở trạng thái {job.status!r}, không complete được")
        job.status = "done"
        job.ended_at = now()
        s.flush()
        return job.as_dict()


def add_job_step(job_id: int, name: str, seq: int = 0) -> dict:
    with db_session() as s:
        step = PrJobStep(job_id=job_id, name=name, seq=seq)
        s.add(step)
        s.flush()
        return step.as_dict()


# --- Count (P-WIP-02) -----------------------------------------------------------
def record_count(station_id: int, qty: int, job_id: int | None = None) -> dict:
    with db_session() as s:
        c = PrCount(station_id=station_id, qty=qty, job_id=job_id)
        s.add(c)
        s.flush()
        return c.as_dict()


def station_total(station_id: int) -> int:
    with db_session() as s:
        stmt = select(func.coalesce(func.sum(PrCount.qty), 0)).where(
            PrCount.station_id == station_id
        )
        return int(s.scalar(stmt) or 0)


# --- Station status (P-WIP-03) --------------------------------------------------
def set_station_status(station_id: int, status: str) -> dict:
    if status not in STATION_STATES:
        raise WipError(f"station status {status!r} không hợp lệ")
    with db_session() as s:
        row = s.get(PrStationStatus, station_id)
        if row is None:
            row = PrStationStatus(station_id=station_id, status=status)
            s.add(row)
        else:
            row.status = status
        s.flush()
        return row.as_dict()


def get_station_status(station_id: int) -> dict | None:
    with db_session() as s:
        row = s.get(PrStationStatus, station_id)
        return row.as_dict() if row else None


# --- Lot link / QR (P-WIP-06) ---------------------------------------------------
def scan_lot(job_id: int, code: str, kind: str = "lot") -> dict:
    with db_session() as s:
        link = PrLotLink(job_id=job_id, code=code, kind=kind)
        s.add(link)
        s.flush()
        return link.as_dict()


def job_lots(job_id: int) -> list[dict]:
    with db_session() as s:
        stmt = select(PrLotLink).where(PrLotLink.job_id == job_id).order_by(PrLotLink.id)
        return [r.as_dict() for r in s.scalars(stmt).all()]
