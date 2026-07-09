"""Runtime persistence bridging the IPN receiver and the stateless subprocesses.

``pending.jsonl`` records renewals awaiting payment; ``renewals.jsonl`` records
finalized ones. Both are gitignored runtime state in the shared ``data/`` volume;
the committed CSVs are never mutated.
"""
from __future__ import annotations

import json
from pathlib import Path


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_pending(rec: dict, path: str | Path | None = None) -> None:
    """Append a pending-renewal record (keyed by ``order_id``)."""
    _append(Path(path) if path else _data_dir() / "pending.jsonl", rec)


def find_pending(order_id: str, path: str | Path | None = None) -> dict | None:
    """Return the newest pending record for ``order_id`` or ``None``."""
    rows = _read(Path(path) if path else _data_dir() / "pending.jsonl")
    matches = [r for r in rows if r.get("order_id") == order_id]
    return matches[-1] if matches else None


def load_renewals(path: str | Path | None = None) -> list[dict]:
    """Return all finalized renewals."""
    return _read(Path(path) if path else _data_dir() / "renewals.jsonl")


def finalize(order_id: str, pending: dict, path: str | Path | None = None) -> bool:
    """Append a finalized renewal for ``order_id``; idempotent.

    Returns True when written, False when ``order_id`` was already finalized.
    """
    p = Path(path) if path else _data_dir() / "renewals.jsonl"
    if any(r.get("order_id") == order_id for r in _read(p)):
        return False
    _append(p, {
        "order_id": order_id,
        "vehicle_id": pending.get("vehicle_id"),
        "col": pending.get("col"),
        "new_expiry": pending.get("new_expiry"),
        "policy_id": pending.get("policy_id"),
        "document_name": pending.get("service_name"),
    })
    return True
