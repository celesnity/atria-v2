"""L4 analytics: periods with auto-generated summaries."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.types import JSON

from engine.db import Base


class PrPeriod(Base):
    __tablename__ = "pr_period"

    id = Column(Integer, primary_key=True)
    scope_path = Column(String, nullable=False, index=True)
    opened_at = Column(DateTime(timezone=True), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    summary = Column(JSON, nullable=True)
