"""Tests for enterprise_knowledge token budgeting helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_budget_uut", _MOD / "budget.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_budget_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_estimate_tokens_positive():
    b = _load()
    assert b.estimate_tokens("hello world") >= 1


def test_input_budget_leaves_room_for_output():
    b = _load()
    assert b.input_budget("synthesis") < b.model_context_limit()


def test_fit_text_truncates_when_over_budget():
    b = _load()
    long = "x " * 10000
    fitted = b.fit_text(long, 10)
    assert b.estimate_tokens(fitted) <= 40  # 10 tokens + truncation marker slack
    assert "truncated" in fitted
