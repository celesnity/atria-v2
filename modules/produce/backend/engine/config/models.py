"""L1 workflow definition: versioned graph JSON + hierarchical reason codes."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.types import JSON

from engine.db import Base


class PrWorkflow(Base):
    __tablename__ = "pr_workflow"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    scope_path = Column(String, nullable=False)
    current_version_id = Column(Integer, nullable=True)


class PrWorkflowVersion(Base):
    __tablename__ = "pr_workflow_version"

    id = Column(Integer, primary_key=True)
    workflow_id = Column(Integer, ForeignKey("pr_workflow.id"), nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(String, nullable=False, default="draft")  # draft|published|retired
    graph = Column(JSON, nullable=False, default=dict)


class PrReasonCode(Base):
    __tablename__ = "pr_reason_code"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("pr_reason_code.id"), nullable=True)
    code = Column(String, nullable=False)
    label = Column(String, nullable=False)
