"""E2 Thực thi có hướng dẫn & e-SOP — pr_* models.

pr_sop + pr_sop_version: SOP có phiên bản, chỉ phát hành bản đã duyệt (P-EXEC-06).
pr_step_confirm: operator xác nhận từng bước + giá trị đo (P-EXEC-02, P-EXEC-04),
poka-yoke chặn khi giá trị ngoài ngưỡng (P-EXEC-03).
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String

from db import Base, now

SOP_VERSION_STATES = ("draft", "approved", "retired")


class PrSop(Base):
    __tablename__ = "pr_sop"
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_id = Column(Integer, ForeignKey("pr_operation.id"), nullable=True)
    code = Column(String(64), nullable=False, unique=True)
    title = Column(String(128), nullable=False)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "code": self.code,
            "title": self.title,
        }


class PrSopVersion(Base):
    __tablename__ = "pr_sop_version"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sop_id = Column(Integer, ForeignKey("pr_sop.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(16), nullable=False, default="draft")
    # steps: [{name, required, media, min, max}] — min/max cho poka-yoke.
    steps = Column(JSON, nullable=False, default=list)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "sop_id": self.sop_id,
            "version": self.version,
            "status": self.status,
            "steps": self.steps or [],
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }


class PrStepConfirm(Base):
    __tablename__ = "pr_step_confirm"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("pr_job.id"), nullable=False)
    sop_version_id = Column(Integer, ForeignKey("pr_sop_version.id"), nullable=True)
    step_index = Column(Integer, nullable=False)
    value = Column(Float, nullable=True)  # giá trị đo tại bước (nếu có)
    confirmed_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "sop_version_id": self.sop_version_id,
            "step_index": self.step_index,
            "value": self.value,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
        }
