"""send_table tool — push a READ-ONLY result table (+ chart suggestions) to chat.

Read-only sibling of ``send_editable_table``. Reads a CSV the analysis wrote into
the session's data_copilot folder and emits the existing ``data_message`` payload
with ``editable: false`` and a ``suggestions`` list, so the web UI renders an
interactive chart + table without any save-back.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def _err(msg: str) -> dict[str, Any]:
    """Build a uniform failure dict for the tool result."""
    return {"success": False, "error": msg, "output": None}


def resolve_session(context: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(session_id, working_dir)`` for the current session, or ``(None, None)``.

    Mirrors the session lookup used by the artifacts handler: the tool execution
    context exposes ``session_manager`` and the current session carries both its
    id and ``working_directory``.
    """
    session_manager = getattr(context, "session_manager", None) if context else None
    if session_manager is None:
        return None, None
    try:
        from atria.db.sync import run_sync

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


class SendTableHandler:
    """Handler for the send_table tool."""

    def _resolve_session(self, context: Any) -> Tuple[Optional[str], Optional[str]]:
        return resolve_session(context)

    def send(self, args: dict[str, Any], context: Any) -> dict[str, Any]:
        file = (args.get("file") or "").strip()
        title = (args.get("title") or "").strip()
        suggestions = args.get("suggestions") or []
        if not file:
            return _err("'file' is required")
        if not title:
            return _err("'title' is required")

        ui_callback = getattr(context, "ui_callback", None)
        if ui_callback is None or not hasattr(ui_callback, "on_data"):
            return _err("UI callback unavailable; send_table only works in the web UI")

        session_id, working_dir = self._resolve_session(context)
        if not session_id or not working_dir:
            return _err("no active session/working_dir to resolve the table path")

        try:
            from atria.core.modules import data_copilot_paths as dcp

            data = dcp.read_session_csv(session_id, working_dir, file)
        except FileNotFoundError:
            return _err(f"table not found: {file!r}")
        except ValueError as exc:
            return _err(str(exc))
        except Exception as exc:  # noqa: BLE001 — surface as a tool error, never crash
            return _err(f"failed to read table: {exc}")

        columns = data.get("columns") or []
        rows = data.get("rows") or []
        max_rows = args.get("max_rows")
        if isinstance(max_rows, int) and max_rows > 0:
            rows = rows[:max_rows]

        payload: dict[str, Any] = {
            "title": title,
            "columns": columns,
            "rows": rows,
            "suggestions": suggestions if isinstance(suggestions, list) else [],
            "editable": False,
        }
        if data.get("warning"):
            payload["warning"] = data["warning"]

        ui_callback.on_data(payload)
        return {
            "success": True,
            "output": f"Sent table ({len(rows)} rows × {len(columns)} cols): {title}",
            "data_payload": payload,
        }
