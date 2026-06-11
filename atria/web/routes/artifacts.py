"""Artifact management endpoints."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from atria.db.connection import get_sessionmaker
from atria.db.repositories.artifact_repo import ArtifactRepository
from atria.db.repositories.conversation_repo import ConversationRepository
from atria.web.dependencies.auth import require_authenticated_user

router = APIRouter(
    prefix="/api/artifacts",
    tags=["artifacts"],
    dependencies=[Depends(require_authenticated_user)],
)

# ── type → icon hint map ───────────────────────────────────────────────────────
_EXT_TO_TYPE: dict[str, str] = {
    ".md": "report",
    ".txt": "report",
    ".pdf": "report",
    ".py": "code",
    ".ts": "code",
    ".tsx": "code",
    ".js": "code",
    ".json": "data",
    ".csv": "data",
    ".yaml": "data",
    ".yml": "data",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".svg": "image",
    ".html": "web",
    ".htm": "web",
}


def _infer_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return _EXT_TO_TYPE.get(ext, "file")


def _serialize(row: Any) -> dict:
    preview = row["preview"]
    if isinstance(preview, str):
        try:
            preview = json.loads(preview)
        except Exception:
            preview = None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "conversation_id": row["conversation_id"],
        "type": row["type"],
        "source_mode": row["source_mode"],
        "title": row["title"],
        "pinned": row["pinned"],
        "payload_ref": row["payload_ref"],
        "preview": preview,
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


class CreateArtifactRequest(BaseModel):
    project_id: Optional[int] = None
    conversation_id: Optional[int] = None
    type: str = "file"
    title: Optional[str] = None
    payload_ref: Optional[str] = None
    source_mode: Optional[str] = "manual"
    pinned: bool = False


class UpdateArtifactRequest(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None
    payload_ref: Optional[str] = None


@router.get("")
async def list_artifacts(
    conversation_id: Optional[int] = Query(None),
    project_id: Optional[int] = Query(None),
    user=Depends(require_authenticated_user),
) -> list[dict]:
    if not conversation_id and not project_id:
        raise HTTPException(status_code=422, detail="conversation_id or project_id required")
    sm = await get_sessionmaker()
    repo = ArtifactRepository(sm)
    if conversation_id:
        rows = await repo.list_by_conversation(conversation_id)
    else:
        rows = await repo.list_by_project(project_id)
    return [_serialize(r) for r in rows]


@router.post("")
async def create_artifact(
    request: CreateArtifactRequest,
    user=Depends(require_authenticated_user),
) -> dict:
    sm = await get_sessionmaker()
    repo = ArtifactRepository(sm)
    artifact_id = await repo.create(
        project_id=request.project_id,
        conversation_id=request.conversation_id,
        type=request.type,
        title=request.title,
        payload_ref=request.payload_ref,
        source_mode=request.source_mode,
        pinned=request.pinned,
    )
    row = await repo.get_by_id(artifact_id)
    return _serialize(row)


@router.patch("/{artifact_id}")
async def update_artifact(
    artifact_id: int,
    request: UpdateArtifactRequest,
    user=Depends(require_authenticated_user),
) -> dict:
    sm = await get_sessionmaker()
    repo = ArtifactRepository(sm)
    await repo.update(
        artifact_id, title=request.title, pinned=request.pinned, payload_ref=request.payload_ref
    )
    row = await repo.get_by_id(artifact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _serialize(row)


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: int,
    user=Depends(require_authenticated_user),
) -> dict:
    sm = await get_sessionmaker()
    repo = ArtifactRepository(sm)
    deleted = await repo.soft_delete(artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"ok": True}


@router.post("/scan")
async def scan_conversation(
    conversation_id: int = Query(...),
    user=Depends(require_authenticated_user),
) -> list[dict]:
    """Auto-discover files in the conversation working directory and create artifacts."""
    sm = await get_sessionmaker()
    conv_repo = ConversationRepository(sm)
    conv = await conv_repo.get_by_id(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    working_dir = conv["working_directory"]
    if not working_dir or not os.path.isdir(working_dir):
        return []

    artifact_repo = ArtifactRepository(sm)
    project_id = conv["project_id"]
    created: list[dict] = []

    working_path = Path(working_dir)

    # Cleanup: drop any legacy artifacts whose payload_ref is stored as an
    # absolute path. The viewer routes refuse absolute paths (see
    # routes/fs.py::_resolve_safe), so those rows can never be opened. We
    # re-insert them below with the relative payload_ref the viewer expects.
    existing = await artifact_repo.list_by_conversation(conversation_id)
    for row in existing:
        ref = row.get("payload_ref") or ""
        if ref.startswith(("/", "\\")):
            await artifact_repo.soft_delete(row["id"])

    for entry in sorted(working_path.rglob("*")):
        if not entry.is_file():
            continue
        # Skip hidden files and common noise — check only parts RELATIVE to working_dir
        # (otherwise paths like /root/.atria/... get skipped because of the leading dot).
        rel_path = entry.relative_to(working_path)
        if any(
            p.startswith(".") or p in {"__pycache__", "node_modules", ".git"}
            for p in rel_path.parts
        ):
            continue
        rel = str(rel_path)
        artifact_type = _infer_type(str(entry))
        artifact_id = await artifact_repo.upsert_by_ref(
            project_id=project_id,
            conversation_id=conversation_id,
            payload_ref=rel,
            type=artifact_type,
            title=entry.name,
            source_mode="auto",
        )
        row = await artifact_repo.get_by_id(artifact_id)
        if row:
            created.append(_serialize(row))

    return created
