"""Tests for the stateful Jupyter kernel executor."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def kernel_mod():
    return _load("kernel", "dc_kernel")


def test_state_persists_across_cells(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r1 = k.run("x = 21")
        assert r1["status"] == "text"
        r2 = k.run("print(x * 2)")
        assert r2["status"] == "text"
        assert "42" in r2["stdout"]
    finally:
        k.shutdown()


def test_error_status_and_message(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r = k.run("raise ValueError('boom')")
        assert r["status"] == "error"
        assert "ValueError" in r["stdout"] or "boom" in r["stdout"]
    finally:
        k.shutdown()


def test_secrets_not_inherited(kernel_mod, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r = k.run("import os; print('KEY:', os.environ.get('OPENAI_API_KEY'))")
        assert "KEY: None" in r["stdout"]
    finally:
        k.shutdown()


def test_replay_rebuilds_state(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        k.replay(["a = 5", "b = a + 1"])
        r = k.run("print(b)")
        assert "6" in r["stdout"]
    finally:
        k.shutdown()


def test_figures_collected(kernel_mod, tmp_path):
    k = kernel_mod.CodeKernel(str(tmp_path))
    try:
        r = k.run(
            "import matplotlib; matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "plt.plot([1,2,3]); plt.savefig('c.png'); print('done')\n"
        )
        assert any(f.endswith("c.png") for f in r["figures"])
    finally:
        k.shutdown()
