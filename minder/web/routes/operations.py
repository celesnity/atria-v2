"""HTTP adapter for the shared Atria operations command surface."""

from __future__ import annotations

import hmac
import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from minder.core.modules.remote import ConnectorUnreachable, RemoteConnector
from minder.operations.ports import OperationsGateway
from minder.operations.service import OperationsService, PendingOperationStore
from minder.web.dependencies.auth import require_authenticated_user

router = APIRouter(prefix="/api/operations", tags=["operations"])


def _principal_from_user(user: Any) -> dict[str, str]:
    return {
        "username": str(getattr(user, "username", "voice-gateway")),
        "email": str(getattr(user, "email", "") or ""),
    }


async def _operation_principal(
    request: Request,
    operation_key: str | None = Header(default=None, alias="X-Celesnity-Operations-Key"),
) -> dict[str, str]:
    configured_key = os.environ.get("CELESNITY_OPERATIONS_KEY")
    if configured_key and operation_key and hmac.compare_digest(configured_key, operation_key):
        return {"username": "minderai-voice", "email": ""}
    return _principal_from_user(await require_authenticated_user(request))


class HttpOperationsGateway(OperationsGateway):
    """Connector implementation; the use case never sees HTTP or SDK details."""

    def __init__(self) -> None:
        self._monitor = RemoteConnector(
            "monitor", os.environ.get("MONITOR_CONNECTOR_URL", "http://127.0.0.1:9310")
        )
        self._optimize = RemoteConnector(
            "optimize_demo", os.environ.get("OPTIMIZE_CONNECTOR_URL", "http://127.0.0.1:9320")
        )

    def read_operational_truth(self, principal: dict[str, str]) -> dict[str, Any]:
        return self._monitor.call_tool("monitor_live_operations", {}, principal=principal)

    def propose(self, action: str, arguments: dict[str, Any], principal: dict[str, str]) -> dict[str, Any]:
        return self._optimize.call_tool(
            action, arguments, principal=principal, autonomy="medium"
        )

    def execute_approved(
        self, action: str, arguments: dict[str, Any], principal: dict[str, str]
    ) -> dict[str, Any]:
        return self._optimize.post_json(
            "/connector/decision",
            {"verdict": "approve", "action": action, "arguments": arguments},
            principal=principal,
        )


_operations = OperationsService(HttpOperationsGateway(), PendingOperationStore())


class ReleaseOrder(BaseModel):
    count: int = Field(ge=1, le=20)
    product: str | None = None
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()), min_length=1)


class ServiceOrder(BaseModel):
    machine_id: str = Field(min_length=1)
    idempotency_key: str = Field(default_factory=lambda: str(uuid4()), min_length=1)


class Decision(BaseModel):
    verdict: str = Field(pattern="^(approve|reject)$")


@router.get("/truth")
def operations_truth(principal: dict[str, str] = Depends(_operation_principal)) -> dict[str, Any]:
    try:
        return _operations.operational_truth(principal)
    except ConnectorUnreachable as exc:
        raise HTTPException(503, f"Monitor is unavailable: {exc}") from exc


@router.post("/orders")
def request_release_order(
    order: ReleaseOrder, principal: dict[str, str] = Depends(_operation_principal)
) -> dict[str, Any]:
    try:
        return _operations.request_operation(
            "optimize_release_product",
            {"count": order.count, "product": order.product},
            order.idempotency_key,
            principal,
        )
    except ConnectorUnreachable as exc:
        raise HTTPException(503, f"Optimize is unavailable: {exc}") from exc


@router.post("/service-orders")
def request_service_order(
    order: ServiceOrder, principal: dict[str, str] = Depends(_operation_principal)
) -> dict[str, Any]:
    try:
        return _operations.request_operation(
            "optimize_service_machine",
            {"machine_id": order.machine_id},
            order.idempotency_key,
            principal,
        )
    except ConnectorUnreachable as exc:
        raise HTTPException(503, f"Optimize is unavailable: {exc}") from exc


@router.post("/{operation_id}/decision")
def decide_operation(operation_id: str, decision: Decision) -> dict[str, Any]:
    try:
        return _operations.decide(operation_id, decision.verdict)
    except KeyError as exc:
        raise HTTPException(404, "operation not found") from exc
    except ConnectorUnreachable as exc:
        raise HTTPException(503, f"Optimize is unavailable: {exc}") from exc
