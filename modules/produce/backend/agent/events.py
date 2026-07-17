"""Track B event registration. Declares the module's event types and forwards the
Track A seam to conn.emit_event (which reaches on_event subscribers + the sink)."""

from __future__ import annotations

import events as seam
from agent.connector import conn

_KINDS = [
    ("job.started", "E01 — a job started"),
    ("job.completed", "E01 — a job completed"),
    ("step.confirmed", "E01 — an SOP step was confirmed"),
    ("downtime.opened", "E02 — a downtime event opened"),
    ("downtime.closed", "E02 — a downtime event closed"),
    ("andon.raised", "E03 — an operator called andon"),
    ("exception.raised", "E05 — a job was blocked (exception raised)"),
]

for _type, _desc in _KINDS:
    conn.event(_type, description=_desc)


def _forward(kind: str, payload: dict) -> None:
    conn.emit_event(kind, payload, source="module")


_attached = False


def attach() -> None:
    """Subscribe the seam forwarder exactly once."""
    global _attached
    if not _attached:
        seam.subscribe(_forward)
        _attached = True
