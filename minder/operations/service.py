"""Use cases for approval-gated laundry operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any, Mapping
from uuid import uuid4

from .ports import OperationsGateway


@dataclass(frozen=True)
class PendingOperation:
    """A command waiting for the same explicit approval Optimize requires."""

    operation_id: str
    idempotency_key: str
    action: str
    arguments: dict[str, Any]
    principal: dict[str, str]
    proposal: dict[str, Any]
    status: str
    outcome: dict[str, Any] | None = None


class PendingOperationStore:
    """Thread-safe local store for short-lived local-development approvals."""

    def __init__(self) -> None:
        self._operations: dict[str, PendingOperation] = {}
        self._by_idempotency_key: dict[str, str] = {}
        self._lock = Lock()

    def find_by_idempotency_key(self, idempotency_key: str) -> PendingOperation | None:
        with self._lock:
            operation_id = self._by_idempotency_key.get(idempotency_key)
            return self._operations.get(operation_id) if operation_id else None

    def save(self, operation: PendingOperation) -> PendingOperation:
        with self._lock:
            self._operations[operation.operation_id] = operation
            self._by_idempotency_key[operation.idempotency_key] = operation.operation_id
            return operation

    def get(self, operation_id: str) -> PendingOperation | None:
        with self._lock:
            return self._operations.get(operation_id)


class OperationsService:
    """Coordinates Monitor reads with Optimize's existing approval boundary."""

    def __init__(self, gateway: OperationsGateway, store: PendingOperationStore) -> None:
        self._gateway = gateway
        self._store = store

    def operational_truth(self, principal: Mapping[str, str]) -> dict[str, Any]:
        return dict(self._gateway.read_operational_truth(principal))

    def request_operation(
        self,
        action: str,
        arguments: Mapping[str, Any],
        idempotency_key: str,
        principal: Mapping[str, str],
    ) -> dict[str, Any]:
        existing = self._store.find_by_idempotency_key(idempotency_key)
        if existing is not None:
            return asdict(existing)

        proposal = dict(self._gateway.propose(action, arguments, principal))
        operation = PendingOperation(
            operation_id=str(uuid4()),
            idempotency_key=idempotency_key,
            action=action,
            arguments=dict(arguments),
            principal=dict(principal),
            proposal=proposal,
            status="awaiting_approval",
        )
        return asdict(self._store.save(operation))

    def decide(self, operation_id: str, verdict: str) -> dict[str, Any]:
        operation = self._store.get(operation_id)
        if operation is None:
            raise KeyError(operation_id)
        if operation.status != "awaiting_approval":
            return asdict(operation)
        if verdict == "reject":
            rejected = PendingOperation(**{**asdict(operation), "status": "rejected"})
            return asdict(self._store.save(rejected))
        outcome = dict(
            self._gateway.execute_approved(operation.action, operation.arguments, operation.principal)
        )
        completed = PendingOperation(
            **{**asdict(operation), "status": "executed", "outcome": outcome}
        )
        return asdict(self._store.save(completed))
