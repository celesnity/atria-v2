"""Tests for the static code guardrail gate."""
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


def test_allows_benign_pandas_code():
    g = _load("guardrails", "dc_guard_ok")
    code = "import pandas as pd\ndf = pd.read_csv('demo.csv')\nprint(df['revenue'].sum())\n"
    verdict = g.check_code(code)
    assert verdict["allowed"] is True
    assert verdict["reasons"] == []


def test_blocks_network_and_subprocess_and_escape():
    g = _load("guardrails", "dc_guard_block")
    for bad in [
        "import requests\nrequests.get('http://x')",
        "import socket",
        "import os\nos.system('rm -rf /')",
        "import subprocess\nsubprocess.run(['ls'])",
        "open('/etc/passwd', 'w')",
        "__import__('os').system('x')",
    ]:
        verdict = g.check_code(bad)
        assert verdict["allowed"] is False, bad
        assert verdict["reasons"], bad
