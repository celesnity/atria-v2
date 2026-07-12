"""Maintenance-copilot web endpoints — the licensed-engineer sign-off.

The copilot is advisory only; a licensed engineer must review a cited answer and
sign off. This records that sign-off (who, what, when, decision) into the same
append-only audit trail the copilot writes, so the human-in-the-loop step is
traceable for airworthiness/compliance.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atria.core.modules.registry import get_registry
from atria.core.modules.remote import ConnectorUnreachable, RemoteConnector
from atria.web.dependencies.auth import require_authenticated_user

router = APIRouter(
    prefix="/api/maintenance",
    tags=["maintenance"],
    dependencies=[Depends(require_authenticated_user)],
)


def _connector() -> RemoteConnector:
    """Build a RemoteConnector from the maintenance_copilot module's manifest."""
    try:
        module = get_registry().get("maintenance_copilot")
    except KeyError as exc:
        raise HTTPException(503, "maintenance_copilot module not loaded") from exc
    svc = module.manifest.service if module.manifest else None
    if not svc:
        raise HTTPException(503, "maintenance_copilot is not configured as a service")
    return RemoteConnector("maintenance_copilot", svc.connector_url, svc.health_path)


class SignoffBody(BaseModel):
    query: str | None = None
    answer_summary: str | None = None
    decision: str = "acknowledged"
    note: str | None = None
    citations: list[dict] | None = None
    answer_type: str | None = None
    is_sensitive: bool | None = None
    exact_quote: str | None = None


def _engineer_of(user: Any) -> str:
    for attr in ("username", "email"):
        val = getattr(user, attr, None)
        if val:
            return str(val)
    if isinstance(user, dict):
        return str(user.get("username") or user.get("email") or "unknown")
    return "unknown"


@router.get("/health")
def maintenance_health() -> dict:
    """Sidecar health, proxied from the maintenance_copilot connector service."""
    try:
        return _connector().get_json("/connector/sidecar-health")
    except ConnectorUnreachable as exc:
        raise HTTPException(503, f"maintenance copilot service unreachable: {exc}") from exc


@router.post("/signoff")
async def signoff(body: SignoffBody, user=Depends(require_authenticated_user)) -> dict:
    """Record a licensed-engineer sign-off; the connector writes the audit trail."""
    payload = {"engineer": _engineer_of(user), **body.model_dump()}
    try:
        return _connector().post_json("/connector/signoff", payload)
    except ConnectorUnreachable as exc:
        raise HTTPException(503, f"sign-off failed (service unreachable): {exc}") from exc
