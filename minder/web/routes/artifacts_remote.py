"""Reverse-push ingress: a service-module attaches an artifact to a session's
conversation. Gated by a Keycloak service principal (module-push)."""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from minder.core.services.artifact_service import ArtifactService
from minder.web.dependencies.service_auth import require_service_principal
from minder.web.dependencies.services import get_artifact_service
from minder.web.state import get_state

router = APIRouter(prefix="/api/artifacts/remote", tags=["artifacts"],
                   dependencies=[Depends(require_service_principal)])


class PushArtifactBody(BaseModel):
    session_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content_b64: str = Field(min_length=1)


@router.post("/push")
async def push_artifact(body: PushArtifactBody,
                        service: ArtifactService = Depends(get_artifact_service)) -> dict:
    session = await get_state().session_manager.get_session_by_id(body.session_id)
    conversation_id = session.metadata.get("conversation_id") if session else None
    if not conversation_id:
        raise HTTPException(404, f"session {body.session_id!r} has no conversation")
    try:
        conv_int = int(conversation_id)
    except (TypeError, ValueError):
        raise HTTPException(404, f"session {body.session_id!r} has an invalid conversation")
    try:
        content = base64.b64decode(body.content_b64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"invalid content_b64: {exc}") from exc
    result = await service.upload_artifact(
        file_content=content, filename=body.filename, content_length=len(content),
        scope="conversation", conversation_id=conv_int, project_id=None)
    try:
        from minder.web.state import broadcast_to_all_clients
        await broadcast_to_all_clients({
            "type": "artifact.changed",
            "scope": "conversation",
            "conversation_id": conv_int,
            "artifact_id": result["artifact_id"],
        })
    except Exception:  # noqa: BLE001 — a failed broadcast must not break the push
        pass
    return {"artifact_id": result["artifact_id"]}
