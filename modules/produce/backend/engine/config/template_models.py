"""Node-template catalog: reusable node definitions scoped to a site/line."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.types import JSON

from engine.db import Base


class PrNodeTemplate(Base):
    __tablename__ = "pr_node_template"

    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=False)
    name = Column(String, nullable=False)
    base_kind = Column(String, nullable=False)
    config = Column(JSON, nullable=False, default=dict)
    color = Column(String, nullable=True)
    icon = Column(String, nullable=True)
    scope_path = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
