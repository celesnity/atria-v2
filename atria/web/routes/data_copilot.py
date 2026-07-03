"""Read/write session-scoped data_copilot CSVs for the editable chat table.

The editable-table bubble binds to a per-session CSV under
``<working_dir>/.artifacts/data_copilot/<session_id>/data/``. These endpoints let
the frontend reload and save-back those files. ``session_id`` is the numeric
conversation id in the web channel, so the working directory is resolved from the
conversation record (mirroring ``routes/artifacts.py``).
"""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from atria.core.modules import data_copilot_paths as dcp

router = APIRouter(prefix="/api/data-copilot", tags=["data-copilot"])


async def _working_dir_for_session(session_id: str) -> str:
    """Resolve a session's working directory. Overridden in tests.

    Uses the conversation record (session_id == conversation id in the web
    channel), matching the resolution in ``routes/artifacts.py``.
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


class WriteBody(BaseModel):
    session_id: str
    file: str
    columns: List[Any] = []
    rows: List[Any] = []


@router.get("/read")
async def read_endpoint(session_id: str = Query(...), file: str = Query(...)) -> dict:
    working_dir = await _working_dir_for_session(session_id)
    try:
        return dcp.read_session_csv(session_id, working_dir, file)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/write")
async def write_endpoint(body: WriteBody) -> dict:
    working_dir = await _working_dir_for_session(body.session_id)
    try:
        return dcp.write_session_csv(
            body.session_id, working_dir, body.file, body.columns, body.rows
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
