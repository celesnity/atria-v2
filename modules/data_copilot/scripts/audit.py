"""Append-only JSONL audit trail for data_copilot analyses.

Each analysis appends one line so every run is traceable: question, dataset,
verification outcome, and retry counts. Location is ``DC_AUDIT_PATH`` if set,
else ``<module_dir>/audit_log.jsonl``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def audit_path() -> Path:
    """Return the audit log path (``DC_AUDIT_PATH`` or module-local default)."""
    override = os.environ.get("DC_AUDIT_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "audit_log.jsonl"


def append_event(event: Dict[str, object]) -> None:
    """Append one JSON event as a line to the audit log.

    Args:
        event: JSON-serializable event payload.
    """
    stamped = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(stamped, default=str) + "\n")


def read_events() -> List[Dict[str, object]]:
    """Read all audit events, oldest first. Empty list if the file is absent.

    Returns:
        The parsed events; malformed lines are skipped.
    """
    path = audit_path()
    if not path.is_file():
        return []
    out: List[Dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
