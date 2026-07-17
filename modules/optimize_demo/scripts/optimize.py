"""Optimize demo — decision persistence CLI (called by the dashboard bridge).

Contract (matches the AtriaDash run gateway):

    python scripts/optimize.py <command>

``<command>`` is argv[1]; the JSON payload arrives on **stdin**; the result is
printed to **stdout** as JSON. The dashboard calls this via
``AtriaDash.json('optimize.py', ['<command>'], { stdin: JSON.stringify(payload) })``.

This layer only persists what the dashboard computed — it never re-derives
forecasts, scores, or constraint results (single source of truth stays in the
dashboard). See store.py.

Commands:
    save      stdin = decision object            -> { ok, decision }
    get       stdin = { recommendation_id, version? } -> { ok, decision }
    list      stdin = {} (ignored)               -> { ok, decisions }
    approve   stdin = { recommendation_id, version?, actor? } -> { ok, decision }
    reject    stdin = { recommendation_id, version?, actor? } -> { ok, decision }
    dispatch  stdin = { recommendation_id, target_module, command?, version?, actor? }
                                                 -> { ok, dispatch }
    outcome   stdin = { recommendation_id, version?, recovered_units?, status? }
                                                 -> { ok, decision }
    audit     stdin = {} (ignored)               -> { ok, audit }

Every command accepts an optional ``at`` (ISO timestamp) so callers can keep
results deterministic; when omitted, lifecycle events are stored without a
timestamp.
"""

from __future__ import annotations

import json
import sys
from typing import Any

try:  # allow both `python scripts/optimize.py` and `python -m ...`
    from . import store
except ImportError:  # pragma: no cover - direct-invocation path
    import store  # type: ignore[no-redef]


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("stdin payload must be a JSON object")
    return data


def _actor(payload: dict[str, Any]) -> dict[str, Any]:
    actor = payload.get("actor")
    if isinstance(actor, dict):
        return actor
    return {"type": "user", "id": "USR-104", "role": "shift_supervisor"}


def handle(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    at = payload.get("at")

    if command == "save":
        decision = payload.get("decision", payload)
        saved = store.save_decision(decision, at=at)
        return {"ok": True, "decision": saved}

    if command == "get":
        rec = store.get_decision(payload["recommendation_id"], payload.get("version"))
        return {"ok": rec is not None, "decision": rec}

    if command == "list":
        return {"ok": True, "decisions": store.load_decisions()}

    if command == "approve":
        rec = store.set_status(
            payload["recommendation_id"],
            "approved",
            version=payload.get("version"),
            event_type="recommendation_approved",
            actor=_actor(payload),
            at=at,
        )
        return {"ok": rec is not None, "decision": rec}

    if command == "reject":
        rec = store.set_status(
            payload["recommendation_id"],
            "rejected",
            version=payload.get("version"),
            event_type="recommendation_rejected",
            actor=_actor(payload),
            at=at,
        )
        return {"ok": rec is not None, "decision": rec}

    if command == "dispatch":
        result = store.dispatch(
            payload["recommendation_id"],
            payload.get("target_module", "move"),
            command=payload.get("command"),
            version=payload.get("version"),
            actor={"type": "system", "id": "optimizer-0.1"},
            at=at,
        )
        return {"ok": result["status"] == "accepted", "dispatch": result}

    if command == "outcome":
        rec = store.set_status(
            payload["recommendation_id"],
            "completed",
            version=payload.get("version"),
            event_type="outcome_recorded",
            actor={"type": "system", "id": "optimizer-0.1"},
            at=at,
            extra={
                "recovered_units": payload.get("recovered_units"),
                "status": payload.get("status", "successful"),
            },
        )
        return {"ok": rec is not None, "decision": rec}

    if command == "audit":
        return {"ok": True, "audit": store.load_audit()}

    return {"ok": False, "error": f"unknown command: {command!r}"}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({"ok": False, "error": "missing command"}))
        return 2
    command = argv[1]
    try:
        payload = _read_payload()
        result = handle(command, payload)
    except KeyError as exc:  # missing required field
        print(json.dumps({"ok": False, "error": f"missing field: {exc}"}))
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
