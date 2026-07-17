"""JSON-file persistence for the Optimize demo — decision history + audit trail.

This layer is deliberately *persistence only*. It never re-derives forecasts,
scores, or constraint results: the dashboard computes the decision object and
this module just versions it, tracks lifecycle status, and appends audit
events. Keeping the decision math in one place (the dashboard) avoids drift.

Storage lives under the module's ``data/`` directory as two JSON files:

- ``decisions.json`` — list of decision records, one per (id, version).
- ``audit.json``     — append-only list of audit-event dicts.

IDs and (optionally) timestamps are derived from the caller's input so tests
are deterministic — no wall-clock or randomness is required.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Terminal lifecycle states that must not be overwritten by a later transition.
_TERMINAL = {"rejected", "completed", "superseded", "expired"}


def data_dir() -> Path:
    """Resolve the module's ``data/`` directory.

    Prefers ``MINDER_MODULE_ROOT`` (set by the dashboard run gateway; the pre-rebrand
    ``ATRIA_MODULE_ROOT`` still works as a deprecated fallback); falls back to the module
    root inferred from this file's location. Honors ``OPTIMIZE_DATA_DIR`` as an explicit
    override (used by tests).
    """
    override = os.environ.get("OPTIMIZE_DATA_DIR")
    if override:
        return Path(override)
    root = os.environ.get("MINDER_MODULE_ROOT") or os.environ.get("ATRIA_MODULE_ROOT")
    base = Path(root) if root else Path(__file__).resolve().parent.parent
    return base / "data"


def _decisions_path() -> Path:
    return data_dir() / "decisions.json"


def _audit_path() -> Path:
    return data_dir() / "audit.json"


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # A truncated / concurrently-written store file must never crash a read (e.g. the Approved
        # History view). Degrade to empty rather than propagating; the next write rewrites it cleanly.
        return []
    return data if isinstance(data, list) else []


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ── decisions ──────────────────────────────────────────────────────────────


def load_decisions() -> list[dict[str, Any]]:
    return _read(_decisions_path())


def _record_key(rec: dict[str, Any]) -> tuple[str, int]:
    return (
        str(rec.get("recommendation_id", "")),
        int(rec.get("recommendation_version", 1) or 1),
    )


def save_decision(decision: dict[str, Any], at: str | None = None) -> dict[str, Any]:
    """Insert or replace a decision by (id, version).

    When the decision carries ``supersedes_version`` (or its version is > 1),
    the referenced prior version is marked ``superseded``. Appends a
    ``recommendation_created`` (or ``recommendation_superseded``) audit event.
    Returns the stored record.
    """
    rec_id = str(decision.get("recommendation_id", ""))
    if not rec_id:
        raise ValueError("decision is missing 'recommendation_id'")
    version = int(decision.get("recommendation_version", 1) or 1)

    rows = load_decisions()
    key = (rec_id, version)
    rows = [r for r in rows if _record_key(r) != key]

    supersedes = decision.get("supersedes_version")
    if supersedes is None and version > 1:
        supersedes = version - 1
    if supersedes is not None:
        prior = (rec_id, int(supersedes))
        for r in rows:
            if _record_key(r) == prior and r.get("status") not in _TERMINAL:
                r["status"] = "superseded"

    rows.append(decision)
    _write(_decisions_path(), rows)

    if supersedes is not None:
        append_audit(
            {
                "event_type": "recommendation_superseded",
                "recommendation_id": rec_id,
                "recommendation_version": version,
                "supersedes_version": int(supersedes),
                "actor": {"type": "system", "id": "optimizer-0.1"},
            },
            at=at,
        )
    else:
        append_audit(
            {
                "event_type": "recommendation_created",
                "recommendation_id": rec_id,
                "recommendation_version": version,
                "actor": {"type": "system", "id": "optimizer-0.1"},
            },
            at=at,
        )
    return decision


def get_decision(rec_id: str, version: int | None = None) -> dict[str, Any] | None:
    """Return one decision. With no version, returns the highest version."""
    matches = [r for r in load_decisions() if str(r.get("recommendation_id")) == rec_id]
    if not matches:
        return None
    if version is not None:
        for r in matches:
            if int(r.get("recommendation_version", 1) or 1) == int(version):
                return r
        return None
    return max(matches, key=lambda r: int(r.get("recommendation_version", 1) or 1))


def set_status(
    rec_id: str,
    status: str,
    version: int | None = None,
    event_type: str | None = None,
    actor: dict[str, Any] | None = None,
    at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update a decision's lifecycle status and append an audit event."""
    rec = get_decision(rec_id, version)
    if rec is None:
        return None
    rec.setdefault("approval", {})
    rec["status"] = status
    # Stamp when the status changed so the recommendation queue can apply a cooldown (don't re-surface
    # a problem the user just acted on before the sim reflects it). Real wall-clock, always present.
    rec["status_at"] = at or _now_iso()
    if status == "approved" and isinstance(rec.get("approval"), dict):
        rec["approval"]["approved_by"] = (actor or {}).get("id")
        if at is not None:
            rec["approval"]["approved_at"] = at

    rows = load_decisions()
    target = (rec_id, int(rec.get("recommendation_version", 1) or 1))
    rows = [rec if _record_key(r) == target else r for r in rows]
    _write(_decisions_path(), rows)

    event: dict[str, Any] = {
        "event_type": event_type or f"recommendation_{status}",
        "recommendation_id": rec_id,
        "recommendation_version": int(rec.get("recommendation_version", 1) or 1),
    }
    if actor is not None:
        event["actor"] = actor
    if extra:
        event.update(extra)
    append_audit(event, at=at)
    return rec


def mock_task_id(target_module: str, rec_id: str, command: dict[str, Any] | None) -> str:
    """Deterministic mock downstream task id (no randomness — stable for tests)."""
    if command and command.get("task"):
        return str(command["task"])
    prefix = (target_module or "move").upper()
    seed = f"{prefix}|{rec_id}|{json.dumps(command or {}, sort_keys=True)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    number = int(digest[:6], 16) % 9000 + 1000
    return f"{prefix}-TASK-{number}"


def dispatch(
    rec_id: str,
    target_module: str,
    command: dict[str, Any] | None = None,
    version: int | None = None,
    actor: dict[str, Any] | None = None,
    at: str | None = None,
) -> dict[str, Any]:
    """Mark a decision dispatched and return a mock downstream acceptance."""
    task_id = mock_task_id(target_module, rec_id, command)
    rec = set_status(
        rec_id,
        "dispatched",
        version=version,
        event_type="command_dispatched",
        actor=actor,
        at=at,
        extra={"target_module": target_module, "task_id": task_id},
    )
    return {
        "status": "accepted" if rec is not None else "unknown-recommendation",
        "recommendation_id": rec_id,
        "target_module": target_module,
        "task_id": task_id,
        "command": command or {},
    }


# ── pipeline snapshots ───────────────────────────────────────────────────────
# One live-fleet snapshot per pipeline run, keyed by execution_id, so a chained run
# (measure -> ... -> recommend) reads the SAME numbers at every stage instead of
# re-polling the drifting simulator. Bounded, gitignored runtime data.

_SNAPSHOTS_MAX = 50


def _snapshots_path() -> Path:
    return data_dir() / "pipeline_runs.json"


def save_snapshot(execution_id: str, snapshot: dict[str, Any], at: str | None = None) -> dict[str, Any]:
    """Persist (or replace) one run snapshot by execution_id; keep the most recent N."""
    if not execution_id:
        raise ValueError("execution_id is required")
    rows = _read(_snapshots_path())
    rows = [r for r in rows if r.get("execution_id") != execution_id]
    row = {"execution_id": execution_id, "snapshot": snapshot, "created_at": at}
    rows.append(row)
    _write(_snapshots_path(), rows[-_SNAPSHOTS_MAX:])
    return row


def get_snapshot(execution_id: str) -> dict[str, Any] | None:
    if not execution_id:
        return None
    for r in _read(_snapshots_path()):
        if r.get("execution_id") == execution_id:
            return r.get("snapshot")
    return None


# ── audit ──────────────────────────────────────────────────────────────────


def load_audit() -> list[dict[str, Any]]:
    return _read(_audit_path())


def append_audit(event: dict[str, Any], at: str | None = None) -> dict[str, Any]:
    event = dict(event)
    if at is not None:
        event.setdefault("timestamp", at)
    rows = load_audit()
    rows.append(event)
    _write(_audit_path(), rows)
    return event
