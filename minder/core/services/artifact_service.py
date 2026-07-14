"""Business logic for artifacts and their on-disk files.

Owns artifact persistence, working-directory resolution, safe file-path
resolution (no traversal), rename/upload/scan orchestration, and response
shaping. Routes call these methods and return the results verbatim.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from minder.core.services.errors import ServiceError
from minder.db.repositories.artifact_repo import ArtifactRepository
from minder.db.repositories.conversation_repo import ConversationRepository
from minder.db.repositories.project_repo import ProjectRepository
from minder.core.utils.file_utils import generate_safe_filename, get_artifact_dir

logger = logging.getLogger(__name__)

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


class ArtifactService:
    """Use cases for the artifacts resource."""

    def __init__(self, sessionmaker: Any) -> None:
        self._sm = sessionmaker
        self._artifacts = ArtifactRepository(sessionmaker)
        self._conversations = ConversationRepository(sessionmaker)
        self._projects = ProjectRepository(sessionmaker)

    async def _resolve_working_dir(self, artifact: dict) -> Optional[str]:
        """Return the base working directory an artifact's files live under.

        Conversation artifacts resolve against the conversation ``working_directory``;
        project artifacts against the project ``workspace_path``. Returns ``None`` when
        the owner record or its directory is missing.
        """
        conversation_id = artifact.get("conversation_id")
        project_id = artifact.get("project_id")
        if conversation_id:
            conv = await self._conversations.get_by_id(conversation_id)
            return conv.get("working_directory") if conv else None
        if project_id:
            proj = await self._projects.get_by_id(project_id)
            return proj.get("workspace_path", "/tmp") if proj else None
        return None

    async def list_artifacts(
        self, conversation_id: Optional[int], project_id: Optional[int]
    ) -> list[dict]:
        if not conversation_id and not project_id:
            raise ServiceError.invalid("conversation_id or project_id required")
        if conversation_id:
            rows = await self._artifacts.list_by_conversation(conversation_id)
        else:
            rows = await self._artifacts.list_by_project(project_id)
        return [_serialize(r) for r in rows]

    async def create_artifact(
        self,
        *,
        project_id: Optional[int],
        conversation_id: Optional[int],
        type: str,
        title: Optional[str],
        payload_ref: Optional[str],
        source_mode: Optional[str],
        pinned: bool,
    ) -> dict:
        artifact_id = await self._artifacts.create(
            project_id=project_id,
            conversation_id=conversation_id,
            type=type,
            title=title,
            payload_ref=payload_ref,
            source_mode=source_mode,
            pinned=pinned,
        )
        row = await self._artifacts.get_by_id(artifact_id)
        return _serialize(row)

    async def update_artifact(
        self,
        artifact_id: int,
        *,
        title: Optional[str],
        pinned: Optional[bool],
        payload_ref: Optional[str],
    ) -> dict:
        await self._artifacts.update(
            artifact_id, title=title, pinned=pinned, payload_ref=payload_ref
        )
        row = await self._artifacts.get_by_id(artifact_id)
        if not row:
            raise ServiceError.not_found("Artifact not found")
        return _serialize(row)

    async def rename_artifact(self, artifact_id: int, new_name: str) -> dict:
        """Rename the physical file backing an artifact and update its DB record.

        Renames within the same parent directory, updates ``payload_ref`` and ``title``.
        Rejects traversal, empty names, and collisions with an existing file.
        """
        artifact = await self._artifacts.get_by_id(artifact_id)
        if not artifact:
            raise ServiceError.not_found("Artifact not found")

        # Sanitize to a bare basename — no directory components, no traversal.
        new_name = Path(new_name.strip()).name
        if not new_name or new_name in (".", ".."):
            raise ServiceError.invalid("Invalid file name")

        working_dir = await self._resolve_working_dir(artifact)
        if not working_dir:
            raise ServiceError.bad_request("Artifact has no working directory")

        src = _resolve_artifact_file(working_dir, artifact)
        if not src or not src.exists():
            raise ServiceError.not_found("Artifact file not found on disk")

        dst = src.with_name(new_name)
        if dst == src:
            return _serialize(artifact)
        if dst.exists():
            raise ServiceError(409, "A file with that name already exists")

        try:
            src.rename(dst)
        except OSError as e:
            logger.error(f"Failed to rename artifact {artifact_id}: {e}", exc_info=True)
            raise ServiceError(500, f"Failed to rename file: {e}") from e

        # payload_ref stays relative to the working dir, matching how the viewer reads it.
        new_ref = str(dst.relative_to(Path(working_dir).resolve()))
        await self._artifacts.update(artifact_id, title=new_name, payload_ref=new_ref)
        row = await self._artifacts.get_by_id(artifact_id)
        return _serialize(row)

    async def upload_artifact(
        self,
        *,
        file_content: bytes,
        filename: Optional[str],
        content_length: Optional[int],
        scope: str,
        conversation_id: Optional[int],
        project_id: Optional[int],
    ) -> dict:
        """Persist an uploaded file as an artifact.

        The caller (route) is responsible for reading the raw bytes off the
        transport; this method validates scope/size, resolves the target
        directory, writes the file, and creates the DB record. Returns a dict
        with the fields the upload response needs.
        """
        # Validate scope
        if scope not in ("conversation", "project"):
            raise ServiceError.invalid("scope must be 'conversation' or 'project'")

        # Validate conversation_id if conversation scope
        if scope == "conversation" and conversation_id is None:
            raise ServiceError.invalid("conversation_id required for conversation scope")

        # Validate project_id if project scope
        if scope == "project" and project_id is None:
            raise ServiceError.invalid("project_id required for project scope")

        # Get working directory based on scope
        if scope == "conversation":
            conv = await self._conversations.get_by_id(conversation_id)
            if not conv:
                raise ServiceError.not_found("Conversation not found")
            working_dir = conv.get("working_directory")
            if not working_dir:
                raise ServiceError.bad_request("Conversation has no working directory")
        else:  # scope == "project"
            proj = await self._projects.get_by_id(project_id)
            if not proj:
                raise ServiceError.not_found("Project not found")
            # Use project workspace_path or a default
            working_dir = proj.get("workspace_path", "/tmp")

        # Check file size (max 50MB) - check header before reading
        max_size = 50 * 1024 * 1024  # 50MB
        if content_length and content_length > max_size:
            raise ServiceError(413, "File too large (max 50MB)")

        if len(file_content) > max_size:
            raise ServiceError(413, "File too large (max 50MB)")

        # Generate safe filename with UUID prefix
        safe_filename = generate_safe_filename(filename or "file")

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
            raise ServiceError(500, f"Failed to save file: {str(e)}") from e

        # Calculate relative path for local_path
        if scope == "conversation":
            local_path = f"conversations/{conversation_id}/{safe_filename}"
        else:
            local_path = f"project/{safe_filename}"

        artifact_type = _infer_type(safe_filename)
        artifact_id = await self._artifacts.create(
            project_id=project_id,
            conversation_id=conversation_id,
            type=artifact_type,
            title=filename or "file",
            scope=scope,
            local_path=local_path,
        )

        # Get artifact record to return full response
        row = await self._artifacts.get_by_id(artifact_id)
        if not row:
            raise ServiceError(500, "Failed to create artifact record")

        return {
            "artifact_id": artifact_id,
            "filename": filename or "file",
            "scope": scope,
            "type": artifact_type,
            "size": len(file_content),
            "created_at": row["created_at"].isoformat(),
        }

    async def delete_artifact(self, artifact_id: int, hard_delete: bool) -> None:
        # Get artifact to retrieve local_path before deletion
        artifact = await self._artifacts.get_by_id(artifact_id)
        if not artifact:
            raise ServiceError.not_found("Artifact not found")

        if hard_delete:
            # Hard delete: remove file from disk. Resolve via payload_ref (viewer path)
            # with a fallback to the legacy .artifacts/local_path layout.
            working_dir = await self._resolve_working_dir(artifact)
            if working_dir:
                full_path = _resolve_artifact_file(working_dir, artifact)
                if full_path and full_path.exists():
                    try:
                        full_path.unlink()
                    except Exception as e:
                        logger.error(f"Failed to delete file {full_path}: {str(e)}")

            # Delete from database
            await self._artifacts.hard_delete(artifact_id)
        else:
            # Soft delete: mark as deleted in DB only
            deleted = await self._artifacts.soft_delete(artifact_id)
            if not deleted:
                raise ServiceError.not_found("Artifact not found")

    async def scan_conversation(self, conversation_id: int) -> list[dict]:
        """Auto-discover files in the conversation working directory and create artifacts."""
        conv = await self._conversations.get_by_id(conversation_id)
        if not conv:
            raise ServiceError.not_found("Conversation not found")

        working_dir = conv["working_directory"]
        if not working_dir or not os.path.isdir(working_dir):
            return []

        project_id = conv["project_id"]
        created: list[dict] = []

        working_path = Path(working_dir)

        # Cleanup: drop any legacy artifacts whose payload_ref is stored as an
        # absolute path. The viewer routes refuse absolute paths (see
        # routes/fs.py::_resolve_safe), so those rows can never be opened. We
        # re-insert them below with the relative payload_ref the viewer expects.
        existing = await self._artifacts.list_by_conversation(conversation_id)
        for row in existing:
            ref = row.get("payload_ref") or ""
            if ref.startswith(("/", "\\")):
                await self._artifacts.soft_delete(row["id"])

        for entry in sorted(working_path.rglob("*")):
            if not entry.is_file():
                continue
            # Skip hidden files and common noise — check only parts RELATIVE to working_dir
            # (otherwise paths like /root/.minder/... get skipped because of the leading dot).
            rel_path = entry.relative_to(working_path)
            if any(
                p.startswith(".") or p in {"__pycache__", "node_modules", ".git"}
                for p in rel_path.parts
            ):
                continue
            rel = str(rel_path)
            artifact_type = _infer_type(str(entry))
            artifact_id = await self._artifacts.upsert_by_ref(
                project_id=project_id,
                conversation_id=conversation_id,
                payload_ref=rel,
                type=artifact_type,
                title=entry.name,
                source_mode="auto",
            )
            row = await self._artifacts.get_by_id(artifact_id)
            if row:
                created.append(_serialize(row))

        return created
