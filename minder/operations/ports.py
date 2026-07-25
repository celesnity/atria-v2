"""Ports owned by the operations use case.

The application layer depends only on this protocol. HTTP connector details live
in the web adapter so the command policy remains independent of transport.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class OperationsGateway(Protocol):
    """Read Monitor facts and ask Optimize to gate or execute a command."""

    def read_operational_truth(self, principal: Mapping[str, str]) -> Mapping[str, Any]: ...

    def propose(self, action: str, arguments: Mapping[str, Any], principal: Mapping[str, str]) -> Mapping[str, Any]: ...

    def execute_approved(
        self, action: str, arguments: Mapping[str, Any], principal: Mapping[str, str]
    ) -> Mapping[str, Any]: ...
