"""E4 Downtime & andon — pr_* models.

pr_downtime: sự kiện dừng máy, mã lý do có cấu trúc Category/Subcategory/Code
(P-DOWN-01), start/end tự động (P-DOWN-03).
pr_andon: operator gọi hỗ trợ (P-DOWN-02); tổ trưởng thấy trạng thái toàn tổ
(P-DOWN-05).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from db import Base, now

ANDON_STATES = ("open", "acknowledged", "resolved")


class PrDowntime(Base):
    __tablename__ = "pr_downtime"
    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=True)
    category = Column(String(64), nullable=False)
    subcategory = Column(String(64), nullable=True)
    code = Column(String(64), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=now)  # tự động
    ended_at = Column(DateTime(timezone=True), nullable=True)  # tự động khi đóng

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "station_id": self.station_id,
            "shift_id": self.shift_id,
            "category": self.category,
            "subcategory": self.subcategory,
            "code": self.code,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class PrDowntimeReason(Base):
    """Thư viện mã lý do downtime theo line/máy (P-DOWN-06) — thu ít mà thu đúng."""

    __tablename__ = "pr_downtime_reason"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    machine = Column(String(64), nullable=True)  # null = áp cho cả line
    category = Column(String(64), nullable=False)
    subcategory = Column(String(64), nullable=True)
    code = Column(String(64), nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "machine": self.machine,
            "category": self.category,
            "subcategory": self.subcategory,
            "code": self.code,
        }


class PrAndon(Base):
    __tablename__ = "pr_andon"
    id = Column(Integer, primary_key=True, autoincrement=True)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    operator_id = Column(String(64), nullable=True)
    reason = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False, default="open")
    raised_at = Column(DateTime(timezone=True), nullable=False, default=now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "station_id": self.station_id,
            "line_id": self.line_id,
            "operator_id": self.operator_id,
            "reason": self.reason,
            "status": self.status,
            "raised_at": self.raised_at.isoformat() if self.raised_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
