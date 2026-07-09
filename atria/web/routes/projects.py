"""Project and conversation management endpoints.

Thin HTTP adapters: parse the request, delegate to :class:`ProjectService`,
return the result. All rules, data access, and orchestration live in the
service; :class:`ServiceError` is mapped to a response by a global handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from atria.core.services.project_service import ProjectService
from atria.web.dependencies.auth import require_authenticated_user
from atria.web.dependencies.services import get_project_service

router = APIRouter(
    prefix="/api/projects",
    tags=["projects"],
    dependencies=[Depends(require_authenticated_user)],
)


class CreateProjectRequest(BaseModel):
    name: str


class CreateConversationRequest(BaseModel):
    name: str


@router.get("")
async def list_projects(
    user=Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> list[dict]:
    return await service.list_projects(user)


@router.post("")
async def create_project(
    request: CreateProjectRequest,
    user=Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> dict:
    return await service.create_project(user, request.name)


@router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    user=Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> dict:
    await service.delete_project(user, project_id)
    return {"ok": True}


@router.get("/{project_id}/conversations")
async def list_conversations(
    project_id: int,
    user=Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> list[dict]:
    return await service.list_conversations(user, project_id)


@router.post("/{project_id}/conversations")
async def create_conversation(
    project_id: int,
    request: CreateConversationRequest,
    user=Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> dict:
    return await service.create_conversation(user, project_id, request.name)


@router.delete("/{project_id}/conversations/{conversation_id}")
async def delete_conversation(
    project_id: int,
    conversation_id: str,
    user=Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> dict:
    await service.delete_conversation(user, project_id, conversation_id)
    return {"ok": True}
