"""Append-only JSONL audit trail for the module."""

from __future__ import annotations

import json
from pathlib import Path


def _default_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "audit.log.jsonl"


def append_event(event: dict, path: str | Path | None = None) -> None:
    """Append one event as a JSON line to the audit log."""
    p = Path(path) if path else _default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def read_events(path: str | Path | None = None) -> list[dict]:
    """Read all events from the audit log (empty list if none)."""
    p = Path(path) if path else _default_path()
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
