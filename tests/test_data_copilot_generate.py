"""Tests for code generation + extraction."""

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


def test_extract_code_from_fenced_block():
    gen = _load("generate", "dc_gen_extract")
    ok, code = gen.extract_code("Here:\n```python\nprint(1)\n```\ndone")
    assert ok is True
    assert "print(1)" in code


def test_extract_code_returns_false_when_absent():
    gen = _load("generate", "dc_gen_noextract")
    ok, code = gen.extract_code("no code here")
    assert ok is False
    assert code == ""


def test_generate_code_passes_profile_and_extracts():
    gen = _load("generate", "dc_gen_full")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return "```python\ndf['revenue'].sum()\n```"

    profile = {
        "path": "demo.csv",
        "n_rows": 8,
        "n_cols": 5,
        "columns": [{"name": "revenue", "dtype": "int64", "non_null": 8, "n_unique": 8}],
        "sample": [],
        "numeric_summary": {},
    }
    code = gen.generate_code("total revenue?", profile, chat_fn)
    assert "revenue" in code
    # the column name is present in the prompt sent to the model (grounding)
    joined = " ".join(m["content"] for m in captured["messages"])
    assert "revenue" in joined and "demo.csv" in joined


def test_prior_error_included_in_repair_prompt():
    gen = _load("generate", "dc_gen_repair")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return "```python\npass\n```"

    gen.generate_code(
        "q",
        {"path": "d", "columns": [], "sample": [], "numeric_summary": {}, "n_rows": 0, "n_cols": 0},
        chat_fn,
        prior_error="NameError: x not defined",
    )
    joined = " ".join(m["content"] for m in captured["messages"])
    assert "NameError" in joined
