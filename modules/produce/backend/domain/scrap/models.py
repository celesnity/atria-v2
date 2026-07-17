"""E5 Phế phẩm, lỗi & rework — pr_* models.

pr_scrap: số lượng phế phẩm + mã lý do lỗi + ảnh (P-SCRAP-01, P-SCRAP-03).
pr_rework: đánh dấu lot cần rework (P-SCRAP-02).
pr_hold: quản ca đặt lot vào trạng thái hold (P-SCRAP-05).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from db import Base, now

HOLD_STATES = ("held", "released")


class PrScrap(Base):
    __tablename__ = "pr_scrap"
    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=True)
    job_id = Column(Integer, ForeignKey("pr_job.id"), nullable=True)
    shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=True)
    qty = Column(Integer, nullable=False, default=0)
    reason_code = Column(String(64), nullable=False)
    photo_ref = Column(String(512), nullable=True)  # key ảnh trong object store
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "station_id": self.station_id,
            "job_id": self.job_id,
            "shift_id": self.shift_id,
            "qty": self.qty,
            "reason_code": self.reason_code,
            "photo_ref": self.photo_ref,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class PrRework(Base):
    __tablename__ = "pr_rework"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lot_code = Column(String(128), nullable=False)
    reason = Column(String(255), nullable=True)
    job_id = Column(Integer, ForeignKey("pr_job.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "lot_code": self.lot_code,
            "reason": self.reason,
            "job_id": self.job_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PrHold(Base):
    """Lot bị hold khi nghi ngờ chất lượng (P-SCRAP-05, quản ca)."""

    __tablename__ = "pr_hold"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lot_code = Column(String(128), nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False, default="held")
    held_by = Column(String(64), nullable=True)
    held_at = Column(DateTime(timezone=True), nullable=False, default=now)
    released_at = Column(DateTime(timezone=True), nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "lot_code": self.lot_code,
            "reason": self.reason,
            "status": self.status,
            "held_by": self.held_by,
            "held_at": self.held_at.isoformat() if self.held_at else None,
            "released_at": self.released_at.isoformat() if self.released_at else None,
        }
