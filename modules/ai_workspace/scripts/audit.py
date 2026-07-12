"""Append-only JSONL audit trail for access decisions, logins, and uploads.

Mirrors the enterprise_knowledge audit format. Path defaults to
``<module>/data/audit.log.jsonl`` and is overridable via ``AIW_AUDIT_LOG``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def default_log_path() -> str:
    """Return ``AIW_AUDIT_LOG`` if set, else ``<module>/data/audit.log.jsonl``."""
    override = os.environ.get("AIW_AUDIT_LOG")
    if override:
        return override
    return str(Path(__file__).resolve().parent.parent / "data" / "audit.log.jsonl")


def append_event(
    event: dict,
    path: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> dict:
    """Stamp ``event`` with a UTC timestamp and append it as one JSON line."""
    target = Path(path or default_log_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    stamped = {"ts": (now_fn or (lambda: datetime.now(timezone.utc)))().isoformat(), **event}
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(stamped, ensure_ascii=False) + "\n")
    return stamped


def read_events(path: str | None = None) -> list[dict]:
    """Read the audit log back into a list (empty if the file is absent)."""
    target = Path(path or default_log_path())
    if not target.is_file():
        return []
    events: list[dict] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events
