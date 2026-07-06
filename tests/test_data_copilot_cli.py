"""Tests for the copilot orchestrator loop + CLI (injected fakes, no real LLM)."""

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


def _fakes():
    prof = {
        "path": "d.csv",
        "n_rows": 1,
        "n_cols": 1,
        "columns": [{"name": "x", "dtype": "int64", "non_null": 1, "n_unique": 1}],
        "sample": [],
        "numeric_summary": {},
    }
    return prof


def test_happy_path_verifies_first_try(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_happy")
    prof = _fakes()
    result = copilot.run_analysis(
        "d.csv",
        "sum?",
        out_dir=str(tmp_path / "run"),
        max_repair=3,
        max_verify=2,
        codegen_fn=lambda q, p, pe=None, hy=None: "print(42)",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "# Report\n42",
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=lambda code, wd, timeout, max_output: {
            "status": "text",
            "stdout": "42",
            "stderr": "",
            "figures": [],
            "returncode": 0,
        },
    )
    assert result["verified"] is True
    assert result["repairs"] == 0
    assert "42" in result["report"]


def test_repairs_execution_error_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_repair")
    prof = _fakes()
    runs = {"n": 0}

    def exec_fn(code, wd, timeout, max_output):
        runs["n"] += 1
        if runs["n"] == 1:
            return {
                "status": "error",
                "stdout": "",
                "stderr": "NameError",
                "figures": [],
                "returncode": 1,
            }
        return {"status": "text", "stdout": "ok", "stderr": "", "figures": [], "returncode": 0}

    result = copilot.run_analysis(
        "d.csv",
        "q",
        out_dir=str(tmp_path / "run"),
        max_repair=3,
        max_verify=2,
        codegen_fn=lambda q, p, pe=None, hy=None: "code",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "r",
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=exec_fn,
    )
    assert result["repairs"] == 1
    assert result["verified"] is True


def test_verify_budget_exhausted_marks_unverified(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_unverified")
    prof = _fakes()
    captured = {}

    def report_fn(q, o, f, verified=True):
        captured["verified"] = verified
        return "r"

    result = copilot.run_analysis(
        "d.csv",
        "q",
        out_dir=str(tmp_path / "run"),
        max_repair=1,
        max_verify=1,
        codegen_fn=lambda q, p, pe=None, hy=None: "code",
        verify_fn=lambda q, c, o: {"status": "REVISE", "hypotheses": "try again"},
        report_fn=report_fn,
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=lambda code, wd, timeout, max_output: {
            "status": "text",
            "stdout": "x",
            "stderr": "",
            "figures": [],
            "returncode": 0,
        },
    )
    assert result["verified"] is False
    assert captured["verified"] is False


def test_guardrail_block_counts_as_repair(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_guard")
    prof = _fakes()
    result = copilot.run_analysis(
        "d.csv",
        "q",
        out_dir=str(tmp_path / "run"),
        max_repair=2,
        max_verify=1,
        codegen_fn=lambda q, p, pe=None, hy=None: "import socket",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "r",
        profile_fn=lambda path: prof,
        guard_fn=lambda code: {"allowed": False, "reasons": ["network"]},
        exec_fn=lambda code, wd, timeout, max_output: {
            "status": "text",
            "stdout": "x",
            "stderr": "",
            "figures": [],
            "returncode": 0,
        },
    )
    # every generation is blocked -> exhausts repair budget -> unverified error
    assert result["verified"] is False
    assert result["status"] == "error"


def test_dataset_path_resolved_to_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_abspath")
    seen = {}

    def profile_fn(path):
        seen["path"] = path
        return {
            "path": path,
            "n_rows": 1,
            "n_cols": 1,
            "columns": [],
            "sample": [],
            "numeric_summary": {},
        }

    copilot.run_analysis(
        "rel.csv",
        "q",
        out_dir=str(tmp_path / "run"),
        max_repair=0,
        max_verify=0,
        codegen_fn=lambda q, p, pe=None, hy=None: "print(1)",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "r",
        profile_fn=profile_fn,
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=lambda code, wd, timeout, max_output: {
            "status": "text",
            "stdout": "1",
            "stderr": "",
            "figures": [],
            "returncode": 0,
        },
    )
    import os

    assert os.path.isabs(seen["path"]), seen["path"]


def test_cli_audit_subcommand_prints_events(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    copilot = _load("copilot", "dc_cli_audit")
    audit = _load("audit", "dc_cli_audit_dep")
    audit.append_event({"type": "analyze", "question": "q1"})
    rc = copilot.main(["audit", "--limit", "10"])
    assert rc == 0
    assert "q1" in capsys.readouterr().out


def test_cli_accepts_file_and_question_flags(capsys):
    """analyze tolerates --file/--question aliases instead of positionals."""
    copilot = _load("copilot", "dc_cli_flags")
    rc = copilot.main(["analyze", "--file", "/tmp/nope.csv", "-q", "hi"])
    out = capsys.readouterr().out
    # Parsed past argparse (no usage crash) and reached dataset resolution.
    assert rc == 1
    assert "dataset not found" in out


def test_cli_persona_defaults_question(capsys):
    """persona with a dataset but no question defaults the request, not errors."""
    copilot = _load("copilot", "dc_cli_persona_default")
    rc = copilot.main(["persona", "--file", "/tmp/nope.csv"])
    out = capsys.readouterr().out
    assert rc == 1
    # Reaches dataset resolution rather than the old 'a question is required'.
    assert "dataset not found" in out
    assert "a question is required" not in out


def test_cli_analyze_missing_question_json_error(capsys):
    """analyze still requires a question and reports it as a clean JSON error."""
    copilot = _load("copilot", "dc_cli_noq")
    rc = copilot.main(["analyze", "/tmp/nope.csv"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "a question is required" in out


def test_cli_missing_dataset_json_error(capsys):
    """Bare persona/analyze with no dataset yields a clean JSON error, not exit-2."""
    copilot = _load("copilot", "dc_cli_nods")
    rc = copilot.main(["persona"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "a dataset is required" in out


def test_cli_analyze_llm_error_is_clean_json(tmp_path, monkeypatch, capsys):
    """A transient LLM/API failure yields a clean JSON error, not a crash.

    The caller parses stdout as JSON; an uncaught traceback would break that
    contract. analyze must catch loop failures and emit {"error": ...}.
    """
    import json

    copilot = _load("copilot", "dc_cli_llm_err")
    csv = tmp_path / "d.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")

    class _Boom:
        def __init__(self, *a, **k):
            pass

        def chat(self, *a, **k):
            raise RuntimeError("rate limit 429")

    monkeypatch.setattr(copilot, "RoleClient", _Boom)
    monkeypatch.setenv("DC_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    rc = copilot.main(["analyze", str(csv), "sum of a?", "--out", str(tmp_path / "run")])
    out = capsys.readouterr().out
    assert rc == 1
    payload = json.loads(out)
    assert "error" in payload
    assert "429" in payload["error"]
