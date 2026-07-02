"""Tests for the bounded subprocess sandbox."""

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


def test_runs_and_captures_stdout(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_ok")
    res = sandbox.run_code("print('answer is', 6*7)", str(tmp_path))
    assert res["status"] == "text"
    assert "answer is 42" in res["stdout"]
    assert res["returncode"] == 0


def test_captures_error(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_err")
    res = sandbox.run_code("raise ValueError('boom')", str(tmp_path))
    assert res["status"] == "error"
    assert "ValueError" in res["stderr"]


def test_timeout_is_enforced(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_timeout")
    res = sandbox.run_code("import time\ntime.sleep(5)", str(tmp_path), timeout=0.5)
    assert res["status"] == "error"
    assert "timeout" in res["stderr"].lower()


def test_collects_figures(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_fig")
    code = (
        "import matplotlib\nmatplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1,2,3]); plt.savefig('chart.png')\n"
        "print('done')\n"
    )
    res = sandbox.run_code(code, str(tmp_path))
    assert res["status"] == "text"
    assert any(f.endswith("chart.png") for f in res["figures"])


def test_output_is_capped(tmp_path):
    sandbox = _load("sandbox", "dc_sandbox_cap")
    res = sandbox.run_code("print('x' * 100000)", str(tmp_path), max_output=1000)
    assert len(res["stdout"]) <= 1000 + 64  # cap + truncation notice slack


def test_reused_workdir_collects_new_and_overwritten_not_stale(tmp_path):
    import os, time

    sandbox = _load("sandbox", "dc_sandbox_reuse")
    old = time.time() - 100
    for n in ("old.png", "chart.png"):
        (tmp_path / n).write_bytes(b"x")
        os.utime(tmp_path / n, (old, old))
    code = (
        "with open('chart.png', 'w') as f: f.write('v2')\n"  # overwrite same name
        "with open('new.png', 'w') as f: f.write('y')\n"  # brand new
        "print('done')\n"
    )
    res = sandbox.run_code(code, str(tmp_path))
    names = {f.split("/")[-1] for f in res["figures"]}
    assert "new.png" in names
    assert "chart.png" in names  # overwritten -> mtime advanced -> collected
    assert "old.png" not in names  # untouched stale -> excluded
