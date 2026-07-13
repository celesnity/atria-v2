"""Artifact management endpoints.

Thin HTTP adapters: parse the request, delegate to :class:`ArtifactService`,
return the result. All rules, data access, file I/O, and orchestration live in
the service; :class:`ServiceError` is mapped to a response by a global handler.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from minder.core.services.artifact_service import ArtifactService
from minder.web.dependencies.auth import require_authenticated_user
from minder.web.dependencies.services import get_artifact_service

router = APIRouter(
    prefix="/api/artifacts",
    tags=["artifacts"],
    dependencies=[Depends(require_authenticated_user)],
)


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


class RenameArtifactRequest(BaseModel):
    new_name: str


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
    service: ArtifactService = Depends(get_artifact_service),
) -> list[dict]:
    return await service.list_artifacts(conversation_id, project_id)


@router.post("")
async def create_artifact(
    request: CreateArtifactRequest,
    user=Depends(require_authenticated_user),
    service: ArtifactService = Depends(get_artifact_service),
) -> dict:
    return await service.create_artifact(
        project_id=request.project_id,
        conversation_id=request.conversation_id,
        type=request.type,
        title=request.title,
        payload_ref=request.payload_ref,
        source_mode=request.source_mode,
        pinned=request.pinned,
    )


@router.patch("/{artifact_id}")
async def update_artifact(
    artifact_id: int,
    request: UpdateArtifactRequest,
    user=Depends(require_authenticated_user),
    service: ArtifactService = Depends(get_artifact_service),
) -> dict:
    return await service.update_artifact(
        artifact_id,
        title=request.title,
        pinned=request.pinned,
        payload_ref=request.payload_ref,
    )


@router.post("/{artifact_id}/rename")
async def rename_artifact(
    artifact_id: int,
    request: RenameArtifactRequest,
    user=Depends(require_authenticated_user),
    service: ArtifactService = Depends(get_artifact_service),
) -> dict:
    return await service.rename_artifact(artifact_id, request.new_name)


@router.post("/upload")
async def upload_artifact(
    file: UploadFile = File(...),
    scope: str = Form(...),
    conversation_id: Optional[int] = Form(None),
    project_id: Optional[int] = Form(None),
    user=Depends(require_authenticated_user),
    service: ArtifactService = Depends(get_artifact_service),
) -> UploadArtifactResponse:
    """Upload a file as an artifact.

    Args:
        file: The file to upload.
        scope: Either "conversation" or "project".
        conversation_id: Required if scope is "conversation".
        project_id: Required if scope is "project".

    Returns:
        Upload response with artifact metadata.
    """
    content_length = file.size if hasattr(file, "size") else None
    file_content = await file.read()
    await file.seek(0)  # Reset file position for potential re-read

    result = await service.upload_artifact(
        file_content=file_content,
        filename=file.filename,
        content_length=content_length,
        scope=scope,
        conversation_id=conversation_id,
        project_id=project_id,
    )
    return UploadArtifactResponse(**result)


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: int,
    hard_delete: bool = Query(False),
    user=Depends(require_authenticated_user),
    service: ArtifactService = Depends(get_artifact_service),
) -> dict:
    """Delete an artifact.

    Args:
        artifact_id: The artifact ID to delete.
        hard_delete: If True, hard delete (file + DB). If False, soft delete (DB only).

    Returns:
        Success response.
    """
    await service.delete_artifact(artifact_id, hard_delete)
    return {"ok": True}


@router.post("/scan")
async def scan_conversation(
    conversation_id: int = Query(...),
    user=Depends(require_authenticated_user),
    service: ArtifactService = Depends(get_artifact_service),
) -> list[dict]:
    """Auto-discover files in the conversation working directory and create artifacts."""
    return await service.scan_conversation(conversation_id)
