"""Artifact management endpoints."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from atria.db.connection import get_sessionmaker
from atria.db.repositories.artifact_repo import ArtifactRepository
from atria.db.repositories.conversation_repo import ConversationRepository
from atria.db.repositories.project_repo import ProjectRepository
from atria.web.dependencies.auth import require_authenticated_user
from atria.web.utils.file_utils import generate_safe_filename, get_artifact_dir

logger = logging.getLogger(__name__)

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


async def _resolve_working_dir(sm: Any, artifact: dict) -> Optional[str]:
    """Return the base working directory an artifact's files live under.

    Conversation artifacts resolve against the conversation ``working_directory``;
    project artifacts against the project ``workspace_path``. Returns ``None`` when
    the owner record or its directory is missing.
    """
    conversation_id = artifact.get("conversation_id")
    project_id = artifact.get("project_id")
    if conversation_id:
        conv = await ConversationRepository(sm).get_by_id(conversation_id)
        return conv.get("working_directory") if conv else None
    if project_id:
        proj = await ProjectRepository(sm).get_by_id(project_id)
        return proj.get("workspace_path", "/tmp") if proj else None
    return None


def _resolve_artifact_file(working_dir: str, artifact: dict) -> Optional[Path]:
    """Resolve the on-disk file for an artifact, safely (no path traversal).

    Prefers ``payload_ref`` (relative to the working dir, as the viewer uses), and
    falls back to the legacy ``.artifacts/local_path`` layout for uploaded files.
    Returns ``None`` if neither ref is set or the resolved path escapes the root.
    """
    base = Path(working_dir).resolve()
    for candidate in (
        artifact.get("payload_ref") and base / artifact["payload_ref"],
        artifact.get("local_path") and base / ".artifacts" / artifact["local_path"],
    ):
        if not candidate:
            continue
        resolved = Path(candidate).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            continue  # traversal attempt — skip
        return resolved
    return None


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


class UploadArtifactRequest(BaseModel):
    scope: str  # "conversation" or "project"
    conversation_id: Optional[int] = None
    project_id: Optional[int] = None


class UploadArtifactResponse(BaseModel):
    artifact_id: int
    filename: str
    scope: str
    type: str
    size: int
    created_at: str


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


class RenameArtifactRequest(BaseModel):
    new_name: str


@router.post("/{artifact_id}/rename")
async def rename_artifact(
    artifact_id: int,
    request: RenameArtifactRequest,
    user=Depends(require_authenticated_user),
) -> dict:
    """Rename the physical file backing an artifact and update its DB record.

    Renames within the same parent directory, updates ``payload_ref`` and ``title``.
    Rejects traversal, empty names, and collisions with an existing file.
    """
    sm = await get_sessionmaker()
    repo = ArtifactRepository(sm)

    artifact = await repo.get_by_id(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Sanitize to a bare basename — no directory components, no traversal.
    new_name = Path(request.new_name.strip()).name
    if not new_name or new_name in (".", ".."):
        raise HTTPException(status_code=422, detail="Invalid file name")

    working_dir = await _resolve_working_dir(sm, artifact)
    if not working_dir:
        raise HTTPException(status_code=400, detail="Artifact has no working directory")

    src = _resolve_artifact_file(working_dir, artifact)
    if not src or not src.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    dst = src.with_name(new_name)
    if dst == src:
        return _serialize(artifact)
    if dst.exists():
        raise HTTPException(status_code=409, detail="A file with that name already exists")

    try:
        src.rename(dst)
    except OSError as e:
        logger.error(f"Failed to rename artifact {artifact_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rename file: {e}") from e

    # payload_ref stays relative to the working dir, matching how the viewer reads it.
    new_ref = str(dst.relative_to(Path(working_dir).resolve()))
    await repo.update(artifact_id, title=new_name, payload_ref=new_ref)
    row = await repo.get_by_id(artifact_id)
    return _serialize(row)


@router.post("/upload")
async def upload_artifact(
    file: UploadFile = File(...),
    scope: str = Form(...),
    conversation_id: Optional[int] = Form(None),
    project_id: Optional[int] = Form(None),
    user=Depends(require_authenticated_user),
) -> UploadArtifactResponse:
    """Upload a file as an artifact.

    Args:
        file: The file to upload.
        scope: Either "conversation" or "project".
        conversation_id: Required if scope is "conversation".
        project_id: Required if scope is "project".

    Returns:
        Upload response with artifact metadata.

    Raises:
        HTTPException: If validation fails, file is too large, or save fails.
    """
    # Validate scope
    if scope not in ("conversation", "project"):
        raise HTTPException(status_code=422, detail="scope must be 'conversation' or 'project'")

    # Validate conversation_id if conversation scope
    if scope == "conversation" and conversation_id is None:
        raise HTTPException(
            status_code=422, detail="conversation_id required for conversation scope"
        )

    # Validate project_id if project scope
    if scope == "project" and project_id is None:
        raise HTTPException(status_code=422, detail="project_id required for project scope")

    sm = await get_sessionmaker()

    # Get working directory based on scope
    if scope == "conversation":
        conv_repo = ConversationRepository(sm)
        conv = await conv_repo.get_by_id(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        working_dir = conv.get("working_directory")
        if not working_dir:
            raise HTTPException(status_code=400, detail="Conversation has no working directory")
    else:  # scope == "project"
        proj_repo = ProjectRepository(sm)
        proj = await proj_repo.get_by_id(project_id)
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        # Use project workspace_path or a default
        working_dir = proj.get("workspace_path", "/tmp")

    # Check file size (max 50MB) - check header before reading
    max_size = 50 * 1024 * 1024  # 50MB
    content_length = file.size if hasattr(file, "size") else None
    if content_length and content_length > max_size:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    # Read file content
    file_content = await file.read()
    if len(file_content) > max_size:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    # Reset file position for potential re-read
    await file.seek(0)

    # Generate safe filename with UUID prefix
    safe_filename = generate_safe_filename(file.filename or "file")

    # Create artifact directory
    artifact_dir = get_artifact_dir(conversation_id, working_dir, scope=scope)
    artifact_path = Path(artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)

    # Write file to disk
    file_path = artifact_path / safe_filename
    try:
        file_path.write_bytes(file_content)
    except Exception as e:
        logger.error(f"Failed to save file {safe_filename}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}") from e

    # Create artifact DB record
    artifact_repo = ArtifactRepository(sm)

    # Calculate relative path for local_path
    if scope == "conversation":
        local_path = f"conversations/{conversation_id}/{safe_filename}"
    else:
        local_path = f"project/{safe_filename}"

    artifact_type = _infer_type(safe_filename)
    artifact_id = await artifact_repo.create(
        project_id=project_id,
        conversation_id=conversation_id,
        type=artifact_type,
        title=file.filename or "file",
        scope=scope,
        local_path=local_path,
    )

    # Get artifact record to return full response
    row = await artifact_repo.get_by_id(artifact_id)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create artifact record")

    return UploadArtifactResponse(
        artifact_id=artifact_id,
        filename=file.filename or "file",
        scope=scope,
        type=artifact_type,
        size=len(file_content),
        created_at=row["created_at"].isoformat(),
    )


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: int,
    hard_delete: bool = Query(False),
    user=Depends(require_authenticated_user),
) -> dict:
    """Delete an artifact.

    Args:
        artifact_id: The artifact ID to delete.
        hard_delete: If True, hard delete (file + DB). If False, soft delete (DB only).

    Returns:
        Success response.

    Raises:
        HTTPException: If artifact not found.
    """
    sm = await get_sessionmaker()
    repo = ArtifactRepository(sm)

    # Get artifact to retrieve local_path before deletion
    artifact = await repo.get_by_id(artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if hard_delete:
        # Hard delete: remove file from disk. Resolve via payload_ref (viewer path)
        # with a fallback to the legacy .artifacts/local_path layout.
        working_dir = await _resolve_working_dir(sm, artifact)
        if working_dir:
            full_path = _resolve_artifact_file(working_dir, artifact)
            if full_path and full_path.exists():
                try:
                    full_path.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete file {full_path}: {str(e)}")

        # Delete from database
        await repo.hard_delete(artifact_id)
    else:
        # Soft delete: mark as deleted in DB only
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
