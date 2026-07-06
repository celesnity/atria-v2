"""Tests for the copilot CLI's non-graph subcommands + parser surface.

`run`/`resume` (the graph-driving subcommands) and the interrupt/resume
mechanism itself are covered in `test_data_copilot_run_resume.py`. `analyze`/
`persona` were retired in favor of `run`/`resume` (Task 11); this file only
asserts they are gone and that the surviving subcommands still work.
"""

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


def test_analyze_and_persona_removed():
    copilot = _load("copilot", "dc_cli_removed")
    parser = copilot.build_parser()
    subs = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert "run" in subs and "resume" in subs
    assert "analyze" not in subs and "persona" not in subs


def test_cli_audit_subcommand_prints_events(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_audit")
    audit = _load("audit", "dc_cli_audit_dep")
    audit.append_event({"type": "run", "question": "q1"})
    rc = copilot.main(["audit", "--limit", "10"])
    assert rc == 0
    assert "q1" in capsys.readouterr().out
