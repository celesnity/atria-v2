"""Maintenance-copilot web endpoints — the licensed-engineer sign-off.

The copilot is advisory only; a licensed engineer must review a cited answer and
sign off. This records that sign-off (who, what, when, decision) into the same
append-only audit trail the copilot writes, so the human-in-the-loop step is
traceable for airworthiness/compliance.
"""

from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from atria.web.dependencies.auth import require_authenticated_user

router = APIRouter(
    prefix="/api/maintenance",
    tags=["maintenance"],
    dependencies=[Depends(require_authenticated_user)],
)

_audit_mod: Any | None = None
_copilot_mod: Any | None = None


def _scripts_on_path() -> None:
    """Put the module's flat scripts dir on sys.path (idempotent)."""
    from atria.core.modules.registry import resolve_modules_root

    scripts = resolve_modules_root() / "maintenance_copilot" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


def _audit() -> Any:
    """Lazily import the maintenance_copilot module's audit helper."""
    global _audit_mod
    if _audit_mod is None:
        _scripts_on_path()
        import audit  # noqa: E402 — flat scripts dir put on sys.path above

        _audit_mod = audit
    return _audit_mod


def _copilot() -> Any:
    """Lazily import the maintenance_copilot CLI module (health probes)."""
    global _copilot_mod
    if _copilot_mod is None:
        _scripts_on_path()
        import copilot  # noqa: E402 — flat scripts dir put on sys.path above

        _copilot_mod = copilot
    return _copilot_mod


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
    """Probe the copilot sidecars (tei/llm/qdrant/neo4j) → 'ok' or 'error: …'.

    Sync on purpose: FastAPI runs it in the threadpool and the probes are
    blocking clients with short timeouts (``MC_HEALTH_TIMEOUT``, default 3s).
    """
    try:
        copilot = _copilot()
        return copilot.check_health(copilot._build_probes())
    except Exception as exc:  # noqa: BLE001 — health must answer, not raise
        raise HTTPException(status_code=500, detail=f"health check failed: {exc}") from exc


@router.post("/signoff")
async def signoff(body: SignoffBody, user=Depends(require_authenticated_user)) -> dict:
    """Record a licensed-engineer sign-off on a copilot answer to the audit trail."""
    try:
        event = _audit().append_event(
            {
                "type": "signoff",
                "engineer": _engineer_of(user),
                "query": body.query,
                "answer_summary": body.answer_summary,
                "decision": body.decision,
                "note": body.note,
                "citations": body.citations or [],
                "answer_type": body.answer_type,
                "is_sensitive": body.is_sensitive,
                "exact_quote": body.exact_quote,
            }
        )
    except Exception as exc:  # noqa: BLE001 — surface audit-write failure to the client
        raise HTTPException(status_code=500, detail=f"sign-off failed: {exc}") from exc
    return {"ok": True, "event": event}
