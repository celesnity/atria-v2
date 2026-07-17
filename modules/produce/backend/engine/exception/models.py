"""L3 exception capture: interrupts, auto-timed."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String

from engine.db import Base


class PrInterrupt(Base):
    __tablename__ = "pr_interrupt"

    id = Column(Integer, primary_key=True)
    work_item_id = Column(Integer, nullable=True)
    step_run_id = Column(Integer, nullable=True)
    scope_path = Column(String, nullable=False, index=True)
    reason_code_id = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="open")  # open|resolved
    started_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    disposition = Column(String, nullable=True)
    raised_by = Column(String, nullable=False)
