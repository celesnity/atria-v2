"""minder-module-sdk — build Minder service-module connectors.

Implements the Minder connector contract v2 (docs/connector-contract.md) so a
module's backend is a few decorated functions instead of hand-rolled FastAPI.
Never imports ``minder``; runs standalone in the module's own container.
"""

from __future__ import annotations

from .cards import assumption, block, card, decision_packet, unavailable_card, unavailable_suffix
from .client import MinderClient, MinderClientError
from .connector import Connector, Principal, ServiceUnavailable
from .envelope import (
    RISK_LADDER,
    EventEnvelope,
    ToolError,
    autonomy_allows,
    make_envelope,
    risk_rank,
)
from . import ui
from .ui import fill, focus, highlight, navigate, request_confirm, submit

__all__ = [
    "MinderClient",
    "MinderClientError",
    "Connector",
    "Principal",
    "ServiceUnavailable",
    "ToolError",
    "EventEnvelope",
    "make_envelope",
    "autonomy_allows",
    "risk_rank",
    "RISK_LADDER",
    "block",
    "card",
    "assumption",
    "decision_packet",
    "unavailable_card",
    "unavailable_suffix",
    "ui",
    "navigate",
    "fill",
    "focus",
    "highlight",
    "request_confirm",
    "submit",
]

__version__ = "0.4.0"
