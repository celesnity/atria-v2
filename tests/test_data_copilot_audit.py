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


def test_append_event_stamps_utc_ts(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    audit = _load("audit", "dc_audit_ts")
    audit.append_event({"type": "analyze", "question": "q"})
    ev = audit.read_events()[0]
    assert "ts" in ev and ev["question"] == "q"


def test_audit_defaults_to_session_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("DC_AUDIT_PATH", raising=False)
    monkeypatch.setenv("ATRIA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ATRIA_CONVERSATION_ID", "sessAAAA")
    monkeypatch.delenv("ATRIA_SESSION_DIR", raising=False)
    audit = _load("audit", "dc_audit_sess")
    audit.append_event({"type": "analyze", "verified": True})
    expected = tmp_path / ".artifacts" / "data_copilot" / "sessAAAA" / "audit.jsonl"
    assert expected.is_file()
    assert audit.read_events()[-1]["type"] == "analyze"
