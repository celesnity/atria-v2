"""Reverse-push ingress for service-modules: mount a federated component in the
chat, or update/remove it. Gated by a Keycloak service principal (module-push).
The subprocess/iframe equivalent lives in ``routes/blocks.py``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from minder.web import ui_bridge
from minder.web.dependencies.service_auth import require_service_principal

router = APIRouter(
    prefix="/api/blocks/remote",
    tags=["blocks"],
    dependencies=[Depends(require_service_principal)],
)


class PushRemoteBody(BaseModel):
    session_id: str = Field(min_length=1)
    module: str = Field(min_length=1)
    remote_name: str = Field(min_length=1)
    remote_entry: str = Field(min_length=1)
    component: str = Field(min_length=1)
    props: Optional[Dict[str, Any]] = None
    block_id: Optional[str] = None
    api_base: Optional[str] = None
    height: Any = "auto"
    title: Optional[str] = None
    persist: bool = True


class UpdateBody(BaseModel):
    session_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    props: Dict[str, Any]


class RemoveBody(BaseModel):
    session_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)


@router.post("/push")
def push(body: PushRemoteBody) -> Dict[str, str]:
    try:
        bid = ui_bridge.push_remote_block(
            module=body.module,
            remote_name=body.remote_name,
            remote_entry=body.remote_entry,
            component=body.component,
            props=body.props,
            block_id=body.block_id,
            api_base=body.api_base,
            height=body.height,
            title=body.title,
            session_id=body.session_id,
            persist=body.persist,
        )
    except RuntimeError as exc:  # no active session
        raise HTTPException(404, str(exc)) from exc
    return {"block_id": bid}


@router.post("/update", status_code=204)
def update(body: UpdateBody) -> None:
    try:
        ui_bridge.update_block(body.block_id, body.props, session_id=body.session_id)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/remove", status_code=204)
def remove(body: RemoveBody) -> None:
    try:
        ui_bridge.remove_block(body.block_id, session_id=body.session_id)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc
