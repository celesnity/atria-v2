"""Tests for the append-only audit trail."""

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


def test_append_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    audit = _load("audit", "dc_audit_rt")
    audit.append_event({"type": "analyze", "question": "q1"})
    audit.append_event({"type": "analyze", "question": "q2"})
    events = audit.read_events()
    assert [e["question"] for e in events] == ["q1", "q2"]


def test_read_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "none.jsonl"))
    audit = _load("audit", "dc_audit_missing")
    assert audit.read_events() == []
