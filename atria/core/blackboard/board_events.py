"""Publish request/bid/response events for the web-ui blackboard viewer.

Distinct from the note channel (``atria:bb:{id}:notes``): board events describe
the request lifecycle (who bid, who volunteered, who answered) rather than
durable findings. Best-effort — publishing never raises to the caller.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_PREFIX = "atria:bb:"


async def publish_board_event(redis: object, run_id: str, kind: str, payload: dict) -> None:
    """Publish ``{kind, **payload}`` JSON to ``atria:bb:{run_id}:board``."""
    channel = f"{_PREFIX}{run_id}:board"
    event = {"kind": kind, **payload}
    try:
        await redis.publish(channel, json.dumps(event))  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 — viewer telemetry is best-effort
        logger.warning("board event publish failed on %s: %s", channel, exc)
