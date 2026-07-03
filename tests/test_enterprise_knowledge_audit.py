from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_audit_uut", _MOD / "audit.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_audit_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_append_then_read_roundtrip(tmp_path):
    a = _load()
    log = tmp_path / "audit.jsonl"
    a.append_event(
        {"type": "query", "user_id": "U004", "role": "Employee",
         "department": "ENG", "permission_decision": "allow"},
        path=str(log), now_fn=lambda: datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    events = a.read_events(str(log))
    assert events[0]["user_id"] == "U004"
    assert events[0]["ts"].startswith("2026-07-03")
