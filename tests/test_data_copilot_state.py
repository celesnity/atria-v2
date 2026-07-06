"""Tests for AgentState shape and verdict constructors."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_agentstate_has_required_keys():
    state = _load("state", "dc_state")
    keys = set(state.AgentState.__annotations__)
    for k in (
        "messages", "user_task", "analysis_plan", "review_status", "review_feedback",
        "review_history", "generated_code", "critic_verdict", "exe_result", "exe_sign",
        "syntax_attempts", "semantic_attempts", "verdict", "inspector_hypotheses",
        "final_report", "error_message", "executed_cells",
    ):
        assert k in keys, f"missing state key: {k}"


def test_verdict_constructor_defaults():
    v = _load("verdict", "dc_verdict")
    assert v.ACCEPT == "ACCEPT" and v.REVISE == "REVISE"
    d = v.new_verdict(v.REVISE, feedback="fix X")
    assert d == {"status": "REVISE", "missing": [], "feedback": "fix X", "epiplexity_score": 0.0}
