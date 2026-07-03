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


def _audit() -> Any:
    """Lazily import the maintenance_copilot module's audit helper."""
    global _audit_mod
    if _audit_mod is None:
        from atria.core.modules.registry import resolve_modules_root

        scripts = resolve_modules_root() / "maintenance_copilot" / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import audit  # noqa: E402 — flat scripts dir put on sys.path above

        _audit_mod = audit
    return _audit_mod


class SignoffBody(BaseModel):
    query: str | None = None
    answer_summary: str | None = None
    decision: str = "acknowledged"
    note: str | None = None
    citations: list[dict] | None = None


def _engineer_of(user: Any) -> str:
    for attr in ("username", "email"):
        val = getattr(user, attr, None)
        if val:
            return str(val)
    if isinstance(user, dict):
        return str(user.get("username") or user.get("email") or "unknown")
    return "unknown"


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
            }
        )
    except Exception as exc:  # noqa: BLE001 — surface audit-write failure to the client
        raise HTTPException(status_code=500, detail=f"sign-off failed: {exc}") from exc
    return {"ok": True, "event": event}
