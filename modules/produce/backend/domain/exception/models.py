"""E9 Ngoại lệ & escalate — pr_* models.

pr_exception: job bị chặn kèm lý do (P-EXCP-01), tổ trưởng phân loại
(P-EXCP-02), quản ca thấy cái đã escalate kèm thời gian mở (P-EXCP-03).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from db import Base, now

# Vòng đời + cấp escalate.
EXCEPTION_STATES = ("open", "triaged", "escalated", "resolved")
# Lý do gợi ý: thiếu vật tư, máy hỏng, chờ QC (P-EXCP-01).


class PrException(Base):
    __tablename__ = "pr_exception"
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_id = Column(Integer, ForeignKey("pr_line.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("pr_task.id"), nullable=True)
    job_id = Column(Integer, ForeignKey("pr_job.id"), nullable=True)
    reason = Column(String(255), nullable=False)
    category = Column(String(64), nullable=True)  # tổ trưởng phân loại (P-EXCP-02)
    status = Column(String(16), nullable=False, default="open")
    raised_by = Column(String(64), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=False, default=now)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "line_id": self.line_id,
            "task_id": self.task_id,
            "job_id": self.job_id,
            "reason": self.reason,
            "category": self.category,
            "status": self.status,
            "raised_by": self.raised_by,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
