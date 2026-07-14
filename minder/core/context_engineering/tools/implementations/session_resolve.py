"""Shared session-resolution helper for tool handlers.

Resolves ``(session_id, working_dir)`` from a tool execution context via the
session manager. Used by the subagent orchestrator wiring.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_session(context: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(session_id, working_dir)`` for the current session, or ``(None, None)``.

    The tool execution context exposes ``session_manager`` and the current
    session carries both its id and ``working_directory``.
    """
    session_manager = getattr(context, "session_manager", None) if context else None
    if session_manager is None:
        return None, None
    try:
        from minder.db.sync import run_sync

        session = run_sync(session_manager.get_current_session())
    except Exception as exc:  # noqa: BLE001 — never crash tool dispatch on lookup
        logger.debug("resolve_session failed: %s", exc)
        return None, None
    if session is None:
        return None, None
    working_dir = getattr(session, "working_directory", None)
    if not working_dir:
        return None, None
    return str(session.id), str(working_dir)
