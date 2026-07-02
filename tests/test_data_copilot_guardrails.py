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


def test_blocks_from_import_comma_and_alias_forms():
    g = _load("guardrails", "dc_guard_forms")
    for bad in [
        "from subprocess import run\nrun(['ls'])",
        "from multiprocessing import Process",
        "from os import system\nsystem('x')",
        "from os import remove\nremove('/etc/passwd')",
        "from shutil import rmtree\nrmtree('/x')",
        "import os, socket",
        "from ftplib import FTP",
        "from smtplib import SMTP",
        "import httpx",
        "import requests as r\nr.get('http://x')",
    ]:
        assert g.check_code(bad)["allowed"] is False, bad


def test_allows_relative_and_read_open():
    g = _load("guardrails", "dc_guard_read")
    assert g.check_code("open('data.csv')\nopen('out.png', 'w')")["allowed"] is True
    assert g.check_code("open('/data/run/in.csv', 'r')")["allowed"] is True


def test_blocks_write_to_absolute_or_parent_paths():
    g = _load("guardrails", "dc_guard_write")
    for bad in ["open('/etc/x', 'w')", "open('../y', 'a')", "open(f'/tmp/{n}', 'w')"]:
        assert g.check_code(bad)["allowed"] is False, bad


def test_ast_ignores_comments_and_strings():
    g = _load("guardrails", "dc_guard_ast_comments")
    assert g.check_code("import pandas as pd  # do not use requests here")["allowed"] is True
    assert g.check_code("x = 'import socket'\nprint(x)")["allowed"] is True


def test_allows_submodule_named_like_forbidden():
    g = _load("guardrails", "dc_guard_submod")
    assert g.check_code("from django.http import HttpResponse")["allowed"] is True


def test_blocks_multiline_parenthesized_dangerous_import():
    g = _load("guardrails", "dc_guard_multiline")
    assert g.check_code("from os import (\n    path,\n    system,\n)")["allowed"] is False
    assert g.check_code("from shutil import (\n    copy,\n    rmtree,\n)")["allowed"] is False


def test_allows_pandas_eval_and_query_methods():
    g = _load("guardrails", "dc_guard_pandas_eval")
    assert g.check_code("df.eval('a + b')\ndf.query('a > 1')")["allowed"] is True


def test_unparseable_code_is_allowed_through():
    g = _load("guardrails", "dc_guard_syntax")
    assert g.check_code("def (:\n  broken")["allowed"] is True


def test_blocks_aliased_os_and_shutil_calls():
    g = _load("guardrails", "dc_guard_alias_calls")
    for bad in [
        "import os as o\no.system('rm -rf /')",
        "import os as o\no.remove('/etc/passwd')",
        "import shutil as sh\nsh.rmtree('/x')",
    ]:
        assert g.check_code(bad)["allowed"] is False, bad
