"""Scope tree flattened to a path string; containment is a prefix match."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Session

from engine.db import Base


class PrScope(Base):
    __tablename__ = "pr_scope"

    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False)
    kind = Column(String, nullable=False)  # resource | line | site | ...
    name = Column(String, nullable=False)


def contains(grant_path: str, target_path: str) -> bool:
    """True if target_path is grant_path or nested under it at a path boundary."""
    return target_path == grant_path or target_path.startswith(grant_path + "/")


def create(session: Session, path: str, kind: str, name: str) -> PrScope:
    row = PrScope(path=path, kind=kind, name=name)
    session.add(row)
    return row
