"""CRUD service for the node-template catalog."""

from __future__ import annotations

from sqlalchemy.orm import Session

from engine.core import auth
from engine.core.auth import Principal
from engine.core.scope import contains
from engine.db import now
from engine.config.template_models import PrNodeTemplate


def list_templates(session: Session, scope_path: str) -> list[PrNodeTemplate]:
    """Return active templates whose scope contains or is contained by scope_path.

    Args:
        session: SQLAlchemy session.
        scope_path: The scope path to filter against.

    Returns:
        List of matching active PrNodeTemplate rows.
    """
    rows = session.query(PrNodeTemplate).filter_by(is_active=True, deleted_at=None).all()
    return [t for t in rows if contains(t.scope_path, scope_path) or contains(scope_path, t.scope_path)]


def create_template(session: Session, principal: Principal, data: dict) -> PrNodeTemplate:
    """Create a new node template, gated on configure permission.

    Args:
        session: SQLAlchemy session.
        principal: The acting principal.
        data: Dict with keys: key, name, base_kind, scope_path, and optionally config/color/icon.

    Returns:
        The newly created PrNodeTemplate (not yet flushed).
    """
    auth.require(principal, "configure", data["scope_path"])
    t = PrNodeTemplate(
        key=data["key"],
        name=data["name"],
        base_kind=data["base_kind"],
        config=data.get("config", {}),
        color=data.get("color"),
        icon=data.get("icon"),
        scope_path=data["scope_path"],
        is_active=True,
        created_by=principal.subject,
        created_at=now(),
        updated_at=now(),
    )
    session.add(t)
    return t


def update_template(session: Session, principal: Principal, tid: int, data: dict) -> PrNodeTemplate:
    """Update mutable fields of a node template, gated on configure permission.

    Args:
        session: SQLAlchemy session.
        principal: The acting principal.
        tid: Template id.
        data: Dict of fields to update (name, config, color, icon).

    Returns:
        The updated PrNodeTemplate.
    """
    t = session.get(PrNodeTemplate, tid)
    auth.require(principal, "configure", t.scope_path)
    for f in ("name", "config", "color", "icon"):
        if f in data:
            setattr(t, f, data[f])
    t.updated_at = now()
    return t


def delete_template(session: Session, principal: Principal, tid: int) -> None:
    """Soft-delete a node template, gated on configure permission.

    Args:
        session: SQLAlchemy session.
        principal: The acting principal.
        tid: Template id to soft-delete.
    """
    t = session.get(PrNodeTemplate, tid)
    auth.require(principal, "configure", t.scope_path)
    t.is_active = False
    t.deleted_at = now()
