"""L2 execution state: work items and their per-step runs."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.types import JSON

from engine.db import Base


class PrWorkItem(Base):
    __tablename__ = "pr_work_item"

    id = Column(Integer, primary_key=True)
    workflow_version_id = Column(Integer, ForeignKey("pr_workflow_version.id"), nullable=False)
    scope_path = Column(String, nullable=False, index=True)
    priority = Column(Integer, nullable=False, default=100)
    status = Column(String, nullable=False, default="queued")
    claimed_by = Column(String, nullable=True)
    current_step_key = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)


class PrStepRun(Base):
    __tablename__ = "pr_step_run"

    id = Column(Integer, primary_key=True)
    work_item_id = Column(Integer, ForeignKey("pr_work_item.id"), nullable=False, index=True)
    step_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")  # active|completed
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    assignee = Column(String, nullable=False)
    output = Column(JSON, nullable=True)
    validated = Column(Boolean, nullable=False, default=False)
    overridden = Column(Boolean, nullable=False, default=False)
    override_reason = Column(String, nullable=True)
    disposition = Column(String, nullable=True)  # null|rework|scrap|accept_as_is
