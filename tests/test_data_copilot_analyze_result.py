"""Tests that analyze emits result.csv + result.meta.json and summary keys."""

import importlib.util
import json
import sys
from pathlib import Path


def _load_copilot():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_copilot", base / "copilot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_run_analysis_emits_result_table_and_suggestions(tmp_path):
    cop = _load_copilot()
    out = tmp_path / "run"
    out.mkdir()

    def fake_exec(code, out_dir, timeout, max_output):
        (Path(out_dir) / "result.csv").write_text(
            "region,revenue\nNorth,10\nSouth,20\n", encoding="utf-8"
        )
        return {"status": "ok", "stdout": "done", "stderr": "", "figures": [], "returncode": 0}

    summary = cop.run_analysis(
        dataset=str(tmp_path / "in.csv"),
        question="rev by region",
        out_dir=str(out),
        max_repair=0,
        max_verify=0,
        codegen_fn=lambda q, p, pe=None, hy=None: "print('x')",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "# report",
        profile_fn=lambda ds: {"columns": []},
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=fake_exec,
    )
    assert summary["result_table"] == str((out / "result.csv").resolve())
    assert summary["suggestions"] and summary["suggestions"][0]["x"] == "region"
    meta = json.loads((out / "result.meta.json").read_text())
    assert meta["columns"][1]["type"] == "number"


def test_run_analysis_no_result_csv(tmp_path):
    cop = _load_copilot()
    out = tmp_path / "run2"
    out.mkdir()

    def fake_exec(code, out_dir, timeout, max_output):
        return {"status": "ok", "stdout": "42", "stderr": "", "figures": [], "returncode": 0}

    summary = cop.run_analysis(
        dataset=str(tmp_path / "in.csv"),
        question="q",
        out_dir=str(out),
        max_repair=0,
        max_verify=0,
        codegen_fn=lambda q, p, pe=None, hy=None: "print(42)",
        verify_fn=lambda q, c, o: {"status": "OK", "hypotheses": ""},
        report_fn=lambda q, o, f, verified=True: "# report",
        profile_fn=lambda ds: {"columns": []},
        guard_fn=lambda code: {"allowed": True, "reasons": []},
        exec_fn=fake_exec,
    )
    assert summary["result_table"] is None
    assert summary["suggestions"] == []
