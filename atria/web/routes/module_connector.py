"""Generic service-module connector passthrough.

Replaces per-module core routes (e.g. the old bespoke ``routes/maintenance.py``)
with one auth-checked proxy that forwards to any service-module's connector.
Modules add domain endpoints (sign-off, exports, admin, sidecar-health) without
ever editing Atria core.

    GET|POST  /api/modules/{name}/connector/{path}   -> forwards to the connector
    GET       /api/modules/{name}/health             -> health + capabilities

The acting user's identity is forwarded to the connector as ``X-Atria-Principal``
(and a module-scoped secret as ``X-Atria-Module-Token`` if configured) by
``RemoteConnector``.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from atria.core.modules.registry import get_registry
from atria.core.modules.remote import ConnectorUnreachable, RemoteConnector
from atria.core.modules.watcher import kick_reconcile
from atria.web.dependencies.auth import require_authenticated_user
from atria.web.dependencies.service_auth import require_module_register

router = APIRouter(prefix="/api/modules", tags=["module-connector"])

# Only allow forwarding to paths under the connector namespace, so this proxy
# can never be pointed at arbitrary internal endpoints of the service.
_ALLOWED_PREFIX = "connector/"


def _connector_for(name: str) -> RemoteConnector:
    try:
        module = get_registry().get(name)
    except KeyError as exc:
        raise HTTPException(404, f"module {name!r} not loaded") from exc
    svc = module.manifest.service if module.manifest else None
    if not svc:
        raise HTTPException(400, f"module {name!r} is not configured as a service")
    return RemoteConnector(name, svc.connector_url, svc.health_path)


def _principal_of(user: Any) -> dict:
    for attr in ("username", "email"):
        val = getattr(user, attr, None)
        if val:
            return {"username": str(getattr(user, "username", val)),
                    "email": str(getattr(user, "email", "") or "")}
    if isinstance(user, dict):
        return {"username": str(user.get("username") or user.get("email") or "unknown"),
                "email": str(user.get("email") or "")}
    return {"username": "unknown", "email": ""}


@router.get("/{name}/health")
def module_health(name: str, _user=Depends(require_authenticated_user)) -> dict:
    """Live health + capabilities for the module's connector (never raises)."""
    return _connector_for(name).health()


@router.api_route("/{name}/connector/{path:path}", methods=["GET", "POST"])
async def connector_passthrough(
    name: str, path: str, request: Request,
    user=Depends(require_authenticated_user),
) -> Any:
    """Forward an auth-checked request to ``/connector/{path}`` on the module."""
    conn = _connector_for(name)
    principal = _principal_of(user)
    target = f"/{_ALLOWED_PREFIX}{path}"
    try:
        if request.method == "GET":
            return conn.get_json(target, principal=principal)
        body = {}
        if await request.body():
            try:
                body = await request.json()
            except ValueError as exc:
                raise HTTPException(400, "request body must be JSON") from exc
        return conn.post_json(target, body, principal=principal)
    except ConnectorUnreachable as exc:
        raise HTTPException(503, f"module {name!r} connector unreachable: {exc}") from exc


# ---------------------------------------------------------------------------
# Runtime self-registration ingress
# ---------------------------------------------------------------------------

class RegisterBody(BaseModel):
    module: str = Field(min_length=1)
    connector_url: str = Field(min_length=1)
    remote_entry: Optional[str] = None
    api_base: Optional[str] = None


class DeregisterBody(BaseModel):
    module: str = Field(min_length=1)


@router.post("/register")
def register_connector(body: RegisterBody, _svc=Depends(require_module_register)) -> dict:
    """Runtime self-registration of a module connector. Health-poll takes over."""
    get_registry().register_connector(
        name=body.module,
        connector_url=body.connector_url,
        remote_entry=body.remote_entry,
        api_base=body.api_base,
    )
    kick_reconcile(body.module)  # reconcile now rather than waiting a poll cycle
    return {"ok": True}


@router.post("/deregister", status_code=204)
def deregister_connector(body: DeregisterBody, _svc=Depends(require_module_register)) -> None:
    get_registry().mark_connector_down(body.module)
