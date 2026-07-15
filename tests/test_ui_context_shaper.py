"""Unit tests for the pure UI-context shaper."""
from __future__ import annotations

from minder.core.modules.ui_context import shape_ui_context

FULL = {
    "module": "produce",
    "autonomy": "low",
    "principal": {"username": "alice", "authenticated": True,
                  "roles": ["op"], "scopes": ["read"]},
    "actions": [
        {"name": "cmd_start", "risk": "medium", "read_only": False,
         "reversible": True, "undo": None, "allowed": False},
    ],
    "ui_snapshot": {
        "page": "operator",
        "data": [{"name": "wip", "description": "WIP count", "value": 12,
                  "truncated": False}],
        "actions": [{"name": "startJob", "description": "Start the job"}],
    },
    "state": [{"name": "inv", "value": {"n": 2}}],
}


def test_shape_full_envelope():
    out = shape_ui_context(FULL)
    assert out["page"] == "operator"
    assert out["data"] == [{"name": "wip", "description": "WIP count", "value": 12}]
    assert out["buttons"] == [{"name": "startJob", "description": "Start the job"}]
    assert out["actions"] == [{"name": "cmd_start", "risk": "medium",
                               "read_only": False, "allowed": False}]
    assert out["autonomy"] == "low"
    assert out["principal"]["username"] == "alice"


def test_shape_missing_ui_snapshot():
    out = shape_ui_context({"autonomy": "high", "actions": [], "ui_snapshot": None})
    assert out["page"] is None
    assert out["data"] == []
    assert out["buttons"] == []
    assert out["actions"] == []
    assert out["principal"] is None


def test_shape_empty_envelope():
    out = shape_ui_context({})
    assert out == {"page": None, "data": [], "buttons": [],
                   "actions": [], "autonomy": None, "principal": None}


def test_shape_preserves_truncated_and_trims_action_fields():
    raw = {
        "actions": [{"name": "a", "risk": "low", "read_only": True,
                     "reversible": True, "undo": "x", "allowed": True}],
        "ui_snapshot": {"page": None,
                        "data": [{"name": "big", "value": "x", "truncated": True}],
                        "actions": []},
    }
    out = shape_ui_context(raw)
    assert out["data"][0]["truncated"] is True
    # trimmed: reversible/undo dropped from the action view
    assert out["actions"][0] == {"name": "a", "risk": "low",
                                 "read_only": True, "allowed": True}
