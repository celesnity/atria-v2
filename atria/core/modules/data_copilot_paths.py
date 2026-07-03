"""Session-scoped CSV read/write for data_copilot, shared by the tools and the
``/api/data-copilot`` route.

The path is keyed by the atria session id and confined to
``<working_dir>/.artifacts/data_copilot/<session_id>/``. This mirrors the
session-keyed root the module's bash-invoked ``scripts/paths.py`` resolves, so
the agent-side tools and the save route address exactly the files the analysis
wrote — with no DB round-trip.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Dict, List

from atria.core.modules import store


def data_copilot_root(session_id: str, working_dir: str) -> Path:
    """Absolute root for a session's data_copilot artifacts."""
    return Path(working_dir) / ".artifacts" / "data_copilot" / str(session_id)


def _resolve_confined(session_id: str, working_dir: str, rel_or_abs: str) -> Path:
    """Resolve a ``data/``-relative name or absolute path, confined to the root."""
    root = data_copilot_root(session_id, working_dir).resolve()
    candidate = Path(rel_or_abs)
    if not candidate.is_absolute():
        candidate = root / "data" / rel_or_abs
    resolved = candidate.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError("path escapes the session data_copilot root")
    return resolved


def read_session_csv(session_id: str, working_dir: str, rel_file: str) -> Dict[str, Any]:
    """Read a CSV → ``{file, columns, rows, warning?}``.

    ``rel_file`` may be a ``data/``-relative name or an absolute path inside the
    session root (e.g. a run dir's ``result.csv``).
    """
    path = _resolve_confined(session_id, working_dir, rel_file)
    raw = path.read_bytes()  # FileNotFoundError propagates to the caller
    reader = csv.reader(io.StringIO(store._decode_csv_bytes(raw)))
    all_rows = list(reader)
    if not all_rows:
        return {"file": rel_file, "columns": [], "rows": []}

    header = [str(c).strip() or f"column_{i + 1}" for i, c in enumerate(all_rows[0])]
    if len(header) > store._MAX_DATA_COLS:
        header = header[: store._MAX_DATA_COLS]

    body = all_rows[1:]
    warning = None
    if len(body) > store._MAX_DATA_ROWS:
        warning = f"Showing first {store._MAX_DATA_ROWS} of {len(body)} rows"
        body = body[: store._MAX_DATA_ROWS]

    rows: List[dict] = [
        {col: (r[i] if i < len(r) else "") for i, col in enumerate(header)} for r in body
    ]
    out: Dict[str, Any] = {
        "file": rel_file,
        "columns": [{"name": h, "type": "string"} for h in header],
        "rows": rows,
    }
    if warning:
        out["warning"] = warning
    return out


def write_session_csv(
    session_id: str, working_dir: str, rel_file: str, columns: Any, rows: Any
) -> Dict[str, Any]:
    """Write edited rows to ``data/<rel_file>`` (atomic). Reuses the store caps."""
    if not rel_file.endswith(".csv"):
        raise ValueError("file must be a .csv")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    if len(rows) > store._MAX_DATA_ROWS:
        raise ValueError(f"too many rows (max {store._MAX_DATA_ROWS})")

    header = store._coerce_header(columns)
    if not header and rows and isinstance(rows[0], dict):
        header = store._coerce_header(list(rows[0].keys()))
    if not header:
        raise ValueError("no columns to write")
    if len(header) > store._MAX_DATA_COLS:
        raise ValueError(f"too many columns (max {store._MAX_DATA_COLS})")

    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each row must be an object")
        writer.writerow(["" if row.get(c) is None else str(row.get(c)) for c in header])
    data = buf.getvalue().encode("utf-8")
    if len(data) > store._MAX_DATA_BYTES:
        raise ValueError(f"dataset exceeds {store._MAX_DATA_BYTES} bytes")

    target = _resolve_confined(session_id, working_dir, rel_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    store._atomic_write_bytes(target, data)
    return {"written": rel_file, "rows": len(rows), "columns": header}
