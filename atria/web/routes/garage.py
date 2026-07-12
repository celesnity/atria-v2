"""Garage work-log endpoints — the explicit session-close action and lookups.

``POST /api/garage/worklogs/{session_id}/generate`` is how a garage repair
session "closes": the conversation transcript is extracted into a structured
WorkLogRecord by ``modules/garage_copilot/scripts/worklog.py`` (LLM extraction
+ JSON store + embedding index). GET endpoints proxy the same CLI so there is
exactly one store implementation. No in-process pipeline import — mirrors the
maintenance route's out-of-process discipline.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from atria.web.dependencies.auth import require_authenticated_user
from atria.web.state import get_state

router = APIRouter(
    prefix="/api/garage",
    tags=["garage"],
    dependencies=[Depends(require_authenticated_user)],
)

_WORKLOG_SCRIPT = (
    Path(__file__).resolve().parents[3] / "modules" / "garage_copilot" / "scripts" / "worklog.py"
)


async def _session_by_id(session_id: str, owner_id: Optional[str] = None):
    """Non-mutating session read (does not switch current_session)."""
    state = get_state()
    try:
        return await state.session_manager.get_session_by_id(session_id, owner_id=owner_id)
    except FileNotFoundError:
        current = await state.session_manager.get_current_session()
        if current and current.id == session_id:
            return current
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


def _worklog_cli(args: list[str]) -> Dict[str, Any]:
    """Run ``worklog.py <args>`` and return its JSON stdout."""
    cmd = [sys.executable, str(_WORKLOG_SCRIPT), *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=503, detail="work-log service timed out")
    if proc.returncode != 0:
        raise HTTPException(
            status_code=503,
            detail=(proc.stderr or proc.stdout or "work-log command failed").strip()[:500],
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="work-log command returned invalid JSON")


def _transcript_of(session: Any) -> str:
    """Render the conversation for extraction: user/assistant turns only."""
    lines: list[str] = []
    for msg in getattr(session, "messages", []):
        role = getattr(getattr(msg, "role", None), "value", "")
        content = getattr(msg, "content", "") or ""
        if role in ("user", "assistant") and content:
            speaker = "Kỹ thuật viên" if role == "user" else "Copilot"
            lines.append(f"{speaker}: {content}")
    return "\n\n".join(lines)


@router.post("/worklogs/{session_id}/generate")
async def generate_worklog(
    session_id: str,
    incomplete: bool = False,
    user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Close a garage session: extract, store, and index its work log."""
    session = await _session_by_id(session_id, owner_id=str(user.id))
    meta = getattr(session, "metadata", None) or {}
    if meta.get("session_type") != "garage":
        raise HTTPException(status_code=400, detail="Not a garage session (no RO anchor)")

    transcript = _transcript_of(session)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        handle.write(transcript)
        transcript_path = handle.name
    try:
        args = [
            "extract",
            "--transcript",
            transcript_path,
            "--session-id",
            str(session.id),
            "--ro",
            str(meta.get("ro_number", "")),
            "--vin",
            str(meta.get("vin", "")),
            "--brand",
            str(meta.get("brand", "")),
            "--technician",
            str(meta.get("technician", "") or ""),
        ]
        if incomplete:
            args.append("--incomplete")
        return _worklog_cli(args)
    finally:
        Path(transcript_path).unlink(missing_ok=True)


@router.get("/worklogs/search")
async def search_worklogs(
    q: str,
    vin: Optional[str] = None,
    brand: Optional[str] = None,
    k: int = 5,
    user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Paraphrase search over stored work logs (human-facing)."""
    args = ["search", q, "--k", str(int(k))]
    if vin:
        args += ["--vin", vin]
    if brand:
        args += ["--brand", brand]
    return _worklog_cli(args)


@router.get("/worklogs/{session_id}")
async def get_worklog(
    session_id: str,
    user=Depends(require_authenticated_user),
) -> Dict[str, Any]:
    """Fetch the structured work log for one session."""
    return _worklog_cli(["get", session_id])
