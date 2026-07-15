"""E1 Giao việc & hàng đợi — pr_* models.

pr_shift (ca) và pr_task (đơn vị giao việc). MVP: hàng đợi theo ưu tiên
(P-WORK-01), nhận & đánh dấu đang làm (P-WORK-02), gán/gán lại (P-WORK-04),
board trạng thái tổ (P-WORK-05).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from db import Base, now

# Trạng thái task.
TASK_STATES = ("queued", "assigned", "in_progress", "blocked", "done")


class PrShift(Base):
    __tablename__ = "pr_shift"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    name = Column(String(64), nullable=False)  # 'Ca A', 'Ca đêm', ...
    supervisor_id = Column(String(64), nullable=True)  # quản ca
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "name": self.name,
            "supervisor_id": self.supervisor_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class PrTask(Base):
    __tablename__ = "pr_task"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    shift_id = Column(Integer, ForeignKey("pr_shift.id"), nullable=True)
    station_id = Column(Integer, ForeignKey("pr_station.id"), nullable=True)
    operation_id = Column(Integer, ForeignKey("pr_operation.id"), nullable=True)
    part_id = Column(Integer, ForeignKey("pr_part.id"), nullable=True)
    assignee_id = Column(String(64), nullable=True)  # operator được gán
    priority = Column(Integer, nullable=False, default=100)  # nhỏ = ưu tiên cao
    status = Column(String(16), nullable=False, default="queued")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now, onupdate=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "shift_id": self.shift_id,
            "station_id": self.station_id,
            "operation_id": self.operation_id,
            "part_id": self.part_id,
            "assignee_id": self.assignee_id,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
