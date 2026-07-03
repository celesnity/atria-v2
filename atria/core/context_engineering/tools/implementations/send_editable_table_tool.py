"""send_editable_table tool — push an *editable* module dataset to the web UI.

Sibling of ``send_data``. Where ``send_data`` renders a read-only chart/table
from any CSV/XLSX, this binds the bubble to a specific module dataset
(``modules/<module>/data/<file>``) and marks it editable. The frontend renders
an inline editable grid; on Save it PUTs the rows back to
``/api/modules/{module}/data/write``, which atomically rewrites the CSV and
reloads the module (so its dashboard reflects the edits).

The payload reuses the existing DATA_MESSAGE pipeline, adding two optional
fields — ``editable: true`` and ``source: {module, file}`` — so any client that
doesn't understand them simply renders the read-only table.
"""

from __future__ import annotations

from typing import Any


def _err(msg: str) -> dict[str, Any]:
    """Build a uniform failure dict for the tool result."""
    return {"success": False, "error": msg, "output": None}


class SendEditableTableHandler:
    """Handler for the send_editable_table tool."""

    def _resolve_session(self, context: Any):
        from atria.core.context_engineering.tools.implementations.send_table_tool import (
            resolve_session,
        )

        return resolve_session(context)

    def send(self, args: dict[str, Any], context: Any) -> dict[str, Any]:
        module = (args.get("module") or "").strip()
        file = (args.get("file") or "").strip()
        title = (args.get("title") or "").strip()
        editable_columns = args.get("editable_columns")

        if not file:
            return _err("'file' is required (path under the module or session data/ dir)")
        if not title:
            return _err("'title' is required")

        ui_callback = getattr(context, "ui_callback", None)
        if ui_callback is None or not hasattr(ui_callback, "on_data"):
            return _err("UI callback unavailable; send_editable_table only works in the web UI")

        # Session-scoped path: when no module (or the data_copilot module) is given
        # and a session is active, bind to the per-session data_copilot CSV.
        if not module or module == "data_copilot":
            session_id, working_dir = self._resolve_session(context)
            if session_id and working_dir:
                return self._send_session(
                    session_id, working_dir, file, title, editable_columns, ui_callback
                )

        if not module:
            return _err("'module' is required (no active session to bind the file to)")

        # Read the dataset from the module store (CSV under modules/<module>/data/).
        try:
            from atria.core.modules.registry import get_registry
            from atria.core.modules import store

            reg = get_registry()
            data = store.read_dataset(reg.root, module, file)
        except FileNotFoundError:
            return _err(f"dataset not found: {file!r} in module {module!r}")
        except Exception as exc:  # noqa: BLE001 — surface as a tool error, never crash
            return _err(f"failed to read dataset: {exc}")

        columns = data.get("columns") or []
        rows = data.get("rows") or []

        # source.file is the path RELATIVE to the module's data/ dir, so the
        # frontend can round-trip it straight back to the read/write routes
        # without re-prefixing. read_dataset returns the data/-prefixed form.
        rel_file = data.get("file", file)
        if rel_file.startswith("data/"):
            rel_file = rel_file[len("data/") :]

        # Per-column editable flags. Default: every column editable; if the agent
        # passed a whitelist, only those are editable.
        allow = None
        if isinstance(editable_columns, list) and editable_columns:
            allow = {str(c) for c in editable_columns}
        for col in columns:
            if isinstance(col, dict):
                col["editable"] = True if allow is None else (col.get("name") in allow)

        payload: dict[str, Any] = {
            "title": title,
            "columns": columns,
            "rows": rows,
            "suggestions": [],
            "editable": True,
            "source": {"module": module, "file": rel_file},
        }
        if data.get("warning"):
            payload["warning"] = data["warning"]

        ui_callback.on_data(payload)

        return {
            "success": True,
            "output": f"Sent editable table ({len(rows)} rows × {len(columns)} cols) for {module}/{file}",
            # data_payload is persisted on the ToolCall and used by the frontend
            # to re-render the editable bubble on session reload (bypasses the LLM).
            "data_payload": payload,
        }

    def _send_session(
        self,
        session_id: str,
        working_dir: str,
        file: str,
        title: str,
        editable_columns: Any,
        ui_callback: Any,
    ) -> dict[str, Any]:
        """Bind the editable grid to a per-session data_copilot CSV.

        Save-back goes to ``/api/data-copilot/write`` via the ``source.session``
        field rather than the module data route.
        """
        from atria.core.modules import data_copilot_paths as dcp

        try:
            data = dcp.read_session_csv(session_id, working_dir, file)
        except FileNotFoundError:
            return _err(f"dataset not found: {file!r}")
        except ValueError as exc:
            return _err(str(exc))
        except Exception as exc:  # noqa: BLE001 — surface as a tool error, never crash
            return _err(f"failed to read dataset: {exc}")

        columns = data.get("columns") or []
        rows = data.get("rows") or []

        allow = None
        if isinstance(editable_columns, list) and editable_columns:
            allow = {str(c) for c in editable_columns}
        for col in columns:
            if isinstance(col, dict):
                col["editable"] = True if allow is None else (col.get("name") in allow)

        payload: dict[str, Any] = {
            "title": title,
            "columns": columns,
            "rows": rows,
            "suggestions": [],
            "editable": True,
            "source": {"session": session_id, "file": file},
        }
        if data.get("warning"):
            payload["warning"] = data["warning"]

        ui_callback.on_data(payload)
        return {
            "success": True,
            "output": (f"Sent editable table ({len(rows)} rows × {len(columns)} cols) for {file}"),
            "data_payload": payload,
        }
