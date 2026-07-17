"""Track A -> Track B event seam. Track A services call emit() after a write.
Default no-op (no subscribers) so Track A runs standalone. The connector (Track B)
subscribes to forward envelopes to Minder. Never raises into the caller."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("produce.events")

_listeners: list[Callable[[str, dict], None]] = []


def subscribe(fn: Callable[[str, dict], None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def unsubscribe(fn: Callable[[str, dict], None]) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def clear() -> None:
    _listeners.clear()


def emit(kind: str, payload: dict) -> None:
    """Fire-and-forget. A listener error is logged, never propagated to the write."""
    for fn in list(_listeners):
        try:
            fn(kind, payload)
        except Exception as exc:  # noqa: BLE001 — a listener must never break a human write
            logger.warning("event listener failed for %s: %s", kind, exc)
