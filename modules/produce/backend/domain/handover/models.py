"""E8 Bàn giao ca — pr_* models.

pr_handover: bản bàn giao cuối ca — sản lượng, việc treo, downtime chưa đóng
(P-HAND-01); ca vào đọc trước khi bắt đầu (P-HAND-02).
pr_carry_forward: downtime bắc qua ranh giới ca, giữ timestamp gốc để không đếm
hai lần (P-HAND-03).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Text

from db import Base, now


class PrHandover(Base):
    __tablename__ = "pr_handover"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    from_shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=False)
    to_shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=True)
    output_count = Column(Integer, nullable=False, default=0)
    pending = Column(JSON, nullable=False, default=list)  # [{task_id, note}]
    open_downtime = Column(JSON, nullable=False, default=list)  # [{downtime_id, ...}]
    notes = Column(Text, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)  # ca vào đã đọc
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "from_shift_id": self.from_shift_id,
            "to_shift_id": self.to_shift_id,
            "output_count": self.output_count,
            "pending": self.pending or [],
            "open_downtime": self.open_downtime or [],
            "notes": self.notes,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PrCarryForward(Base):
    """Downtime bắc qua ranh giới ca — giữ timestamp gốc (P-HAND-03)."""

    __tablename__ = "pr_carry_forward"
    id = Column(Integer, primary_key=True, autoincrement=True)
    downtime_id = Column(Integer, ForeignKey("pr_downtime.id"), nullable=False)
    from_shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=False)
    to_shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=False)
    original_started_at = Column(DateTime(timezone=True), nullable=False)  # timestamp gốc, không đổi
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "downtime_id": self.downtime_id,
            "from_shift_id": self.from_shift_id,
            "to_shift_id": self.to_shift_id,
            "original_started_at": self.original_started_at.isoformat()
            if self.original_started_at
            else None,
        }
