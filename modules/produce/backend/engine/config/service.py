"""Draft validation, publish (freeze snapshot), and revert."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from engine.config import contract
from engine.config.models import PrWorkflow, PrWorkflowVersion
from engine.core import auth
from engine.core.auth import Principal
from engine.db import now


def validate_draft(session: Session, workflow_id: int) -> list[str]:
    """Return validation issues for the workflow's current draft graph.

    Args:
        session: Active SQLAlchemy session.
        workflow_id: PK of the PrWorkflow to validate.

    Returns:
        List of issue strings; empty list means the draft is valid.
    """
    wf = session.get(PrWorkflow, workflow_id)
    return contract.validate_graph(wf.draft_graph or {"nodes": [], "edges": []})


def publish(
    session: Session,
    principal: Principal,
    workflow_id: int,
    note: str = "",
) -> PrWorkflowVersion:
    """Freeze the current draft graph as an immutable published version.

    Args:
        session: Active SQLAlchemy session.
        principal: Caller principal (must have 'configure' on the workflow's scope).
        workflow_id: PK of the PrWorkflow to publish.
        note: Optional human-readable note attached to the version.

    Returns:
        The newly created PrWorkflowVersion (status='published').

    Raises:
        PermissionError: If principal lacks 'configure' on the workflow scope.
        ValueError: If the draft graph fails validation (issues joined by '; ').
    """
    wf = session.get(PrWorkflow, workflow_id)
    auth.require(principal, "configure", wf.scope_path)
    issues = contract.validate_graph(wf.draft_graph or {"nodes": [], "edges": []})
    if issues:
        raise ValueError("; ".join(issues))
    n = (
        session.query(func.max(PrWorkflowVersion.version))
        .filter_by(workflow_id=wf.id)
        .scalar()
        or 0
    )
    v = PrWorkflowVersion(
        workflow_id=wf.id,
        version=n + 1,
        status="published",
        graph=wf.draft_graph,
        note=note or None,
        published_by=principal.subject,
        published_at=now(),
    )
    session.add(v)
    session.flush()
    wf.current_version_id = v.id
    return v


def revert(
    session: Session,
    principal: Principal,
    workflow_id: int,
    version: int,
) -> PrWorkflow:
    """Copy a previously published version's graph back into the workflow's draft.

    Args:
        session: Active SQLAlchemy session.
        principal: Caller principal (must have 'configure' on the workflow's scope).
        workflow_id: PK of the PrWorkflow to revert.
        version: Version number to restore as the new draft.

    Returns:
        The mutated PrWorkflow (draft_graph updated in-place).

    Raises:
        PermissionError: If principal lacks 'configure' on the workflow scope.
        sqlalchemy.orm.exc.NoResultFound: If the requested version does not exist.
    """
    wf = session.get(PrWorkflow, workflow_id)
    auth.require(principal, "configure", wf.scope_path)
    v = (
        session.query(PrWorkflowVersion)
        .filter_by(workflow_id=wf.id, version=version)
        .one()
    )
    wf.draft_graph = v.graph
    return wf
