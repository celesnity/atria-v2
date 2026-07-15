"""minder-python-sdk — build Minder service-module connectors.

Implements the Minder connector contract v2 (docs/connector-contract.md) so a
module's backend is a few decorated functions instead of hand-rolled FastAPI.
Never imports ``minder``; runs standalone in the module's own container.
"""

from __future__ import annotations

from .cards import assumption, block, card, decision_packet, unavailable_card, unavailable_suffix
from .client import MinderClient, MinderClientError
from .connector import Connector, Principal, ServiceUnavailable
from .context import Note  # noqa: F401
from ._response import ActionError, Response
from ._secret import OAuth2Secret, Secret, SecretSpec
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
    "Note",
    "Response",
    "ActionError",
    "Secret",
    "OAuth2Secret",
    "SecretSpec",
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

__version__ = "0.5.0"
