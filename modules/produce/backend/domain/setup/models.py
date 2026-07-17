"""E7 Setup & changeover — pr_* models.

pr_changeover: checklist đổi sản phẩm + thời gian changeover (P-SETUP-01/02).
pr_first_piece: kiểm first-piece sau setup trước khi chạy loạt (P-SETUP-03).
Cập nhật standard khi đổi sản phẩm (P-SETUP-04) = gán part_id mới cho changeover.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String

from db import Base, now


class PrChangeover(Base):
    __tablename__ = "pr_changeover"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=True)
    from_part_id = Column(Integer, ForeignKey("pr_part.id"), nullable=True)
    to_part_id = Column(Integer, ForeignKey("pr_part.id"), nullable=False)  # standard mới
    checklist = Column(JSON, nullable=False, default=list)  # [{name, done}]
    started_at = Column(DateTime(timezone=True), nullable=False, default=now)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "station_id": self.station_id,
            "from_part_id": self.from_part_id,
            "to_part_id": self.to_part_id,
            "checklist": self.checklist or [],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class PrFirstPiece(Base):
    __tablename__ = "pr_first_piece"
    id = Column(Integer, primary_key=True, autoincrement=True)
    changeover_id = Column(Integer, ForeignKey("pr_changeover.id"), nullable=False)
    passed = Column(Boolean, nullable=False, default=False)
    note = Column(String(255), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "changeover_id": self.changeover_id,
            "passed": self.passed,
            "note": self.note,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }
