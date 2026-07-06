"""Tests for the `run`/`resume` graph-driving CLI (Task 11).

Error paths use bare CLI invocations (no LLM/kernel reached). The interrupt ->
resume mechanism itself is proven end-to-end against a real SqliteSaver with a
fake RoleClient and a fake CodeKernel standing in for the LLM and the Jupyter
process, so no network call or real kernel spawn happens in this suite.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
if str(_MOD) not in sys.path:
    sys.path.insert(0, str(_MOD))


def _load(n, s):
    spec = importlib.util.spec_from_file_location(s, _MOD / f"{n}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[s] = m
    spec.loader.exec_module(m)
    return m


def test_run_missing_dataset_is_clean_json(capsys):
    cop = _load("copilot", "dc_cli_run_err")
    rc = cop.main(["run", "/tmp/nope.csv", "segment"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and "error" in out


def test_resume_requires_thread(capsys):
    cop = _load("copilot", "dc_cli_resume_err")
    rc = cop.main(["resume", "--feedback", "approve"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and "error" in out


def test_resume_requires_feedback(capsys):
    cop = _load("copilot", "dc_cli_resume_err2")
    rc = cop.main(["resume", "--thread", "abc123"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1 and "error" in out


def test_resume_unknown_thread_is_clean_json(tmp_path, monkeypatch, capsys):
    cop = _load("copilot", "dc_cli_resume_unknown")
    monkeypatch.setattr(cop.paths_mod, "checkpoint_db", lambda: tmp_path / "checkpoints.sqlite")
    rc = cop.main(["resume", "--thread", "does-not-exist", "--feedback", "approve"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert "no checkpointed run" in out["error"]


class _FakeRoleClient:
    """Canned per-prompt replies so the graph runs end-to-end with no real LLM.

    Dispatches on the distinctive text of each node's prompt (see prompts.py):
    the planner, classifier, and critic prompts are unique enough to key off of
    directly; anything asking for "complete Python code" (generate_code) gets a
    trivial persona-JSON-emitting script.
    """

    def __init__(self, *_a, **_k):
        self.calls = []

    def chat(self, role, messages, **_kw):
        self.calls.append(role)
        text = "\n".join((m.get("content") or "") for m in messages)
        if "Data Analytics Planner" in text:
            return "## Plan\n1. Load the dataset.\n2. Count the rows and print the total."
        if "Review Classifier" in text:
            return "APPROVE"
        if "Python Code Critic" in text:
            return "PASS"
        if "Generate the complete Python code" in text:
            return (
                "```python\n"
                "print('[JSON_START_PERSONA]')\n"
                "print('[]')\n"
                "print('[JSON_END_PERSONA]')\n"
                "```"
            )
        return "# Report\nDone."


class _FakeCodeKernel:
    """Stands in for kernel.CodeKernel — no real Jupyter process spawns."""

    def __init__(self, workdir):
        self.workdir = workdir

    def run(self, code):
        return {
            "status": "text",
            "stdout": "[JSON_START_PERSONA][][JSON_END_PERSONA]",
            "figures": [],
        }

    def replay(self, cells):
        pass

    def shutdown(self):
        pass


def test_interrupt_then_resume_round_trips_through_sqlite_checkpoint(tmp_path, monkeypatch):
    """Proves the human_review interrupt -> resume mechanism works against a
    real (temp-dir) SqliteSaver, with a fake LLM and fake kernel so no network
    call or real Jupyter process is involved."""
    cop = _load("copilot", "dc_run_resume_it")
    monkeypatch.setattr(cop, "RoleClient", _FakeRoleClient)
    monkeypatch.setattr(cop.paths_mod, "checkpoint_db", lambda: tmp_path / "checkpoints.sqlite")

    import kernel as kernel_mod  # resolves to the real module cached under sys.modules["kernel"]

    monkeypatch.setattr(kernel_mod, "CodeKernel", _FakeCodeKernel)

    dataset = tmp_path / "d.csv"
    dataset.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    out_dir = tmp_path / "run"
    out_dir.mkdir()

    started = cop.run_graph(
        str(dataset),
        "count the rows",
        out_dir=str(out_dir),
        domain=None,
        k=None,
        thread_id="it-thread-1",
    )
    assert started["status"] == "awaiting_review"
    assert started["thread_id"] == "it-thread-1"
    assert started["plan"]

    finished = cop.run_graph(
        str(dataset),
        "count the rows",
        out_dir=str(out_dir),
        domain=None,
        k=None,
        thread_id="it-thread-1",
        resume_feedback="approve",
    )
    assert finished["status"] == "done"
    assert finished["thread_id"] == "it-thread-1"
    assert finished["report"]


def test_cli_run_then_resume_end_to_end(tmp_path, monkeypatch, capsys):
    """Same mechanism as above, but driven through main() (`run` then `resume`)
    to prove the CLI wiring (dataset resolution, checkpoint persistence of
    run_dir/dataset, `resume`'s state readback) works, not just run_graph."""
    cop = _load("copilot", "dc_cli_run_resume_e2e")
    monkeypatch.setattr(cop, "RoleClient", _FakeRoleClient)
    monkeypatch.setattr(cop.paths_mod, "checkpoint_db", lambda: tmp_path / "checkpoints.sqlite")

    import kernel as kernel_mod

    monkeypatch.setattr(kernel_mod, "CodeKernel", _FakeCodeKernel)

    dataset = tmp_path / "d.csv"
    dataset.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    out_dir = tmp_path / "run"

    rc = cop.main(
        [
            "run",
            str(dataset),
            "count the rows",
            "--out",
            str(out_dir),
            "--thread",
            "e2e-thread-1",
        ]
    )
    assert rc == 0
    started = json.loads(capsys.readouterr().out)
    assert started["status"] == "awaiting_review"
    assert started["thread_id"] == "e2e-thread-1"

    rc = cop.main(["resume", "--thread", "e2e-thread-1", "--feedback", "approve"])
    assert rc == 0
    finished = json.loads(capsys.readouterr().out)
    assert finished["status"] == "done"
    assert finished["report"]


def test_run_graph_persists_report_and_read_report_reads_it_back(tmp_path, monkeypatch):
    """Proves the CRITICAL seam: run_graph must write report.md to out_dir on
    `done`, and return a `run_dir` in the session-root-relative form
    (`runs/<name>`) that `atria.core.modules.data_copilot_paths.read_report`
    can resolve — the same seam `send_report` and the `/api/data-copilot/report`
    route depend on. Neither this test nor run_graph hand-writes report.md
    anywhere except through run_graph's own persistence code path.
    """
    from atria.core.modules import data_copilot_paths as dcp

    cop = _load("copilot", "dc_run_graph_report_persist")
    monkeypatch.setattr(cop, "RoleClient", _FakeRoleClient)
    monkeypatch.setattr(cop.paths_mod, "checkpoint_db", lambda: tmp_path / "checkpoints.sqlite")

    import kernel as kernel_mod

    monkeypatch.setattr(kernel_mod, "CodeKernel", _FakeCodeKernel)

    # Align data_copilot_paths.data_copilot_root(session_id, working_dir) with
    # paths.conversation_root() (ATRIA_WORKSPACE + ATRIA_CONVERSATION_ID) so the
    # writer (run_graph, driven by scripts/paths.py's conversation_root()) and the
    # reader (data_copilot_paths.read_report) resolve to the *same* directory.
    session_id = "sess-report-e2e"
    working_dir = tmp_path / "workspace"
    working_dir.mkdir()
    monkeypatch.setenv("ATRIA_WORKSPACE", str(working_dir))
    monkeypatch.setenv("ATRIA_CONVERSATION_ID", session_id)

    root = dcp.data_copilot_root(session_id, str(working_dir))
    out_dir = root / "runs" / "run-report-e2e"
    out_dir.mkdir(parents=True)

    dataset = tmp_path / "d.csv"
    dataset.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    started = cop.run_graph(
        str(dataset),
        "count the rows",
        out_dir=str(out_dir),
        domain=None,
        k=None,
        thread_id="report-e2e-thread",
    )
    assert started["status"] == "awaiting_review"

    finished = cop.run_graph(
        str(dataset),
        "count the rows",
        out_dir=str(out_dir),
        domain=None,
        k=None,
        thread_id="report-e2e-thread",
        resume_feedback="approve",
    )
    assert finished["status"] == "done"
    assert finished["run_dir"] == "runs/run-report-e2e"

    report_file = out_dir / "report.md"
    assert report_file.exists()
    assert report_file.read_text(encoding="utf-8") == finished["report"]
    assert finished["report"]

    # The reader side: data_copilot_paths.read_report, pointed at the same
    # session root via env, must read exactly what run_graph wrote.
    read_back = dcp.read_report(session_id, str(working_dir), finished["run_dir"])
    assert read_back["report"] == finished["report"]
