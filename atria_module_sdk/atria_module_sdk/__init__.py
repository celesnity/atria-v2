"""atria-module-sdk — build Atria service-module connectors.

Implements the Atria connector contract v2 (docs/connector-contract.md) so a
module's backend is a few decorated functions instead of hand-rolled FastAPI.
Never imports ``atria``; runs standalone in the module's own container.
"""
from __future__ import annotations

from .cards import block, card, unavailable_card, unavailable_suffix
from .connector import Connector, Principal, ServiceUnavailable

__all__ = [
    "Connector",
    "Principal",
    "ServiceUnavailable",
    "block",
    "card",
    "unavailable_card",
    "unavailable_suffix",
]

__version__ = "0.1.0"
