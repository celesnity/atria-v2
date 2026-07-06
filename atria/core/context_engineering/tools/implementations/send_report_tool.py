"""send_report tool — push a data_copilot run's report markdown to chat.

Read-only sibling of ``send_table``: instead of a CSV, this reads the
``report.md`` a data_copilot LangGraph run wrote (via
:func:`atria.core.modules.data_copilot_paths.read_report`) and emits a
``data_message`` payload the web UI renders as a report bubble.
"""

from __future__ import annotations

import logging
from typing import Any

from atria.core.modules import data_copilot_paths as dcp

logger = logging.getLogger(__name__)


def _err(msg: str) -> dict[str, Any]:
    """Build a uniform failure dict for the tool result."""
    return {"success": False, "error": msg, "output": None}


def _build_payload(session_id: str, working_dir: str, run_dir: str) -> dict[str, Any]:
    """Read ``report.md`` for ``run_dir`` and build the chat payload.

    Raises:
        FileNotFoundError: If the run's ``report.md`` does not exist.
    """
    data = dcp.read_report(session_id, working_dir, run_dir)
    return {"type": "report", "report": data["report"], "run_dir": run_dir}


class SendReportHandler:
    """Handler for the send_report tool."""

    def _resolve_session(self, context: Any):
        from atria.core.context_engineering.tools.implementations.send_table_tool import (
            resolve_session,
        )

        return resolve_session(context)

    def send(self, args: dict[str, Any], context: Any) -> dict[str, Any]:
        run_dir = (args.get("run_dir") or "").strip()
        if not run_dir:
            return _err("'run_dir' is required")

        ui_callback = getattr(context, "ui_callback", None)
        if ui_callback is None or not hasattr(ui_callback, "on_data"):
            return _err("UI callback unavailable; send_report only works in the web UI")

        session_id, working_dir = self._resolve_session(context)
        if not session_id or not working_dir:
            return _err("no active session/working_dir to resolve the report path")

        try:
            payload = _build_payload(
                session_id=session_id, working_dir=working_dir, run_dir=run_dir
            )
        except FileNotFoundError:
            return _err(f"report not found for run_dir {run_dir!r}")
        except Exception as exc:  # noqa: BLE001 — surface as a tool error, never crash
            return _err(f"failed to read report: {exc}")

        ui_callback.on_data(payload)
        return {
            "success": True,
            "output": f"Sent report ({len(payload['report'])} chars) for {run_dir}",
            "data_payload": payload,
        }
