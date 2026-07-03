"""Persist per-session chart display overrides for the interactive chat charts.

The web UI renders agent-recommended charts (from ``send_table`` suggestions) with
Recharts and lets the user tweak title, series labels, colors, chart type, etc.
Those edits ("overrides") are keyed by the stable ``chart_id`` the ``send_table``
tool stamps on each chart, and stored in a single JSON file per session so they
survive a reload without mutating the immutable tool-call history.

Storage: ``<data_copilot_root>/chart_overrides.json`` → ``{chart_id: {...}}``.
``session_id`` is the numeric conversation id in the web channel, matching
``routes/data_copilot.py``.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from atria.core.modules import data_copilot_paths as dcp

router = APIRouter(prefix="/api/charts", tags=["charts"])

_OVERRIDES_FILE = "chart_overrides.json"


async def _working_dir_for_session(session_id: str) -> str:
    """Resolve a session's working directory. Overridden in tests.

    Uses the conversation record (session_id == conversation id in the web
    channel), matching the resolution in ``routes/data_copilot.py``.
    """
    from atria.db.connection import get_sessionmaker
    from atria.db.repositories.conversation_repo import ConversationRepository

    try:
        conv_id = int(session_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid session id")

    sm = await get_sessionmaker()
    conv = await ConversationRepository(sm).get_by_id(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    working_dir = conv.get("working_directory")
    if not working_dir:
        raise HTTPException(status_code=400, detail="conversation has no working directory")
    return str(working_dir)


def _overrides_path(session_id: str, working_dir: str):
    return dcp.data_copilot_root(session_id, working_dir) / _OVERRIDES_FILE


def _load_all(session_id: str, working_dir: str) -> Dict[str, Any]:
    path = _overrides_path(session_id, working_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class OverridesBody(BaseModel):
    session_id: str
    chart_id: str
    overrides: Dict[str, Any]


@router.get("/overrides")
async def get_overrides(session_id: str = Query(...)) -> Dict[str, Any]:
    """Return the full ``{chart_id: overrides}`` map for a session."""
    working_dir = await _working_dir_for_session(session_id)
    return _load_all(session_id, working_dir)


@router.put("/overrides")
async def put_overrides(body: OverridesBody) -> dict:
    """Merge one chart's overrides into the session's overrides file."""
    if not body.chart_id:
        raise HTTPException(status_code=422, detail="chart_id is required")
    working_dir = await _working_dir_for_session(body.session_id)
    all_overrides = _load_all(body.session_id, working_dir)
    all_overrides[body.chart_id] = body.overrides
    path = _overrides_path(body.session_id, working_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(all_overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "chart_id": body.chart_id}
