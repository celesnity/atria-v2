"""A grant binds a subject (Keycloak/Minder id) to a role within a scope."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String

from engine.db import Base


class PrGrant(Base):
    __tablename__ = "pr_grant"

    id = Column(Integer, primary_key=True)
    subject = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    scope_id = Column(Integer, ForeignKey("pr_scope.id"), nullable=False)
