"""Risk/autonomy gating and the event envelope — the two things that make an
Minder module safe to *act* through (moat: the SDK gate) and accountable *after*
it acts (moat: the ground-truth envelope).

Nothing here imports ``minder`` or does I/O; it is pure data + ordering so it can
be unit-tested and reused by the connector, the client, and modules.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# --- risk / autonomy ---------------------------------------------------------

# A single ordered ladder used for BOTH a tool's risk and the caller's autonomy.
# An action is allowed to auto-execute when its risk rank <= the caller's
# autonomy rank; otherwise the SDK gates it (returns a decision packet instead of
# running the handler). ``none`` is for pure reads — never gated.
RISK_LADDER = ("none", "low", "medium", "high", "critical")


def risk_rank(level: Optional[str]) -> int:
    """Rank a risk/autonomy name; unknown names are treated as the safest (0)."""
    try:
        return RISK_LADDER.index((level or "none").lower())
    except ValueError:
        return 0


def autonomy_allows(risk: Optional[str], autonomy: Optional[str]) -> bool:
    """True when a caller at ``autonomy`` may auto-execute an action of ``risk``."""
    return risk_rank(risk) <= risk_rank(autonomy)


def normalize_risk(level: Optional[str]) -> str:
    """Coerce to a known ladder name (default ``low`` for actions, callers pass
    ``none`` explicitly for reads)."""
    lvl = (level or "low").lower()
    return lvl if lvl in RISK_LADDER else "low"


# --- structured errors -------------------------------------------------------


class ToolError(Exception):
    """Raise from a handler to fail with a *structured* error the agent can act on
    (recover / escalate) instead of a bare string.

        raise ToolError("not_dispatchable", "MEL item expired", retryable=False)
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def as_error(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


# --- event envelope (ground truth) ------------------------------------------


@dataclass
class EventEnvelope:
    """A normalized, timestamped, sourced record of something that happened.

    Every action a module (or the agent acting through it) performs emits one of
    these to Minder's event log, so the Operational Graph stays the source of
    truth even when the actor is an agent rather than a human.
    """

    module: str
    type: str
    payload: dict = field(default_factory=dict)
    event_id: str = ""
    ts: str = ""
    source: str = "module"
    actor: Optional[dict] = None
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "module": self.module,
            "ts": self.ts,
            "source": self.source,
            "actor": self.actor,
            "session_id": self.session_id,
            "payload": self.payload,
        }


def make_envelope(
    module: str,
    event_type: str,
    payload: Optional[dict] = None,
    *,
    source: str = "module",
    actor: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> EventEnvelope:
    """Build an :class:`EventEnvelope` stamped with a fresh id + UTC timestamp."""
    return EventEnvelope(
        module=module,
        type=event_type,
        payload=payload or {},
        event_id=uuid.uuid4().hex,
        ts=datetime.now(timezone.utc).isoformat(),
        source=source,
        actor=actor,
        session_id=session_id,
    )


def actor_from(principal: Any, agent_id: Optional[str]) -> dict:
    """Compose the ``actor`` block: who acted, distinguishing agent vs human.

    ``kind`` is ``agent`` when an agent id is present (the agent acted on the
    user's behalf), else ``human`` when a real user is known, else ``system``.
    """
    username = getattr(principal, "username", "unknown")
    is_auth = getattr(principal, "is_authenticated", False)
    kind = "agent" if agent_id else ("human" if is_auth else "system")
    return {
        "kind": kind,
        "agent_id": agent_id,
        "on_behalf_of": username if is_auth else None,
    }
