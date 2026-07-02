"""Tests for semantic verification parsing + flow."""
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


def test_parse_ok():
    v = _load("verify", "dc_verify_ok")
    assert v.parse_verdict("STATUS: OK\nThe output answers the question.")["status"] == "OK"


def test_parse_revise_captures_hypotheses():
    v = _load("verify", "dc_verify_rev")
    out = v.parse_verdict("STATUS: REVISE\nHYPOTHESES: group by region first")
    assert out["status"] == "REVISE"
    assert "group by region" in out["hypotheses"]


def test_parse_defaults_to_revise_when_unclear():
    v = _load("verify", "dc_verify_default")
    assert v.parse_verdict("hmm not sure")["status"] == "REVISE"


def test_verify_calls_model_and_returns_verdict():
    v = _load("verify", "dc_verify_flow")
    out = v.verify("q", "code", "output", lambda m: "STATUS: OK")
    assert out["status"] == "OK"
