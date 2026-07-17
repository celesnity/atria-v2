"""Shape a module connector's ``/connector/context`` envelope into a compact,
LLM-friendly view of the live UI (page, on-screen data, buttons, tool actions)."""

from __future__ import annotations

from typing import Any


def _shape_data(entry: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": entry.get("name"),
        "description": entry.get("description"),
        "value": entry.get("value"),
    }
    if entry.get("truncated"):
        out["truncated"] = True
    return out


def _shape_button(entry: dict[str, Any]) -> dict[str, Any]:
    return {"name": entry.get("name"), "description": entry.get("description")}


def _shape_action(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": entry.get("name"),
        "risk": entry.get("risk"),
        "read_only": entry.get("read_only"),
        "allowed": entry.get("allowed"),
    }


def shape_ui_context(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a ``fetch_context()`` envelope into the agent-facing UI view.

    Total and side-effect free: a missing or ``None`` ``ui_snapshot`` yields an
    empty page/data/buttons; missing ``actions``/``principal`` yield ``[]``/``None``.

    Args:
        raw: The ``/connector/context`` response dict.

    Returns:
        ``{page, data, buttons, actions, autonomy, principal}``.
    """
    snapshot = raw.get("ui_snapshot") or {}
    data = snapshot.get("data") or []
    buttons = snapshot.get("actions") or []
    actions = raw.get("actions") or []
    return {
        "page": snapshot.get("page"),
        "data": [_shape_data(d) for d in data if isinstance(d, dict)],
        "buttons": [_shape_button(b) for b in buttons if isinstance(b, dict)],
        "actions": [_shape_action(a) for a in actions if isinstance(a, dict)],
        "autonomy": raw.get("autonomy"),
        "principal": raw.get("principal"),
    }
