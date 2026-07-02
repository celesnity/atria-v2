"""Tests for grounded report generation."""
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


def test_report_includes_output_and_figures_in_prompt():
    report = _load("report", "dc_report_prompt")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return "# Report\nTotal revenue is 24600."

    md = report.generate_report("total revenue?", "revenue sum: 24600",
                                 ["/runs/chart.png"], chat_fn)
    assert "Report" in md
    joined = " ".join(m["content"] for m in captured["messages"])
    assert "24600" in joined and "chart.png" in joined


def test_unverified_prepends_warning():
    report = _load("report", "dc_report_unverified")
    md = report.generate_report("q", "partial output", [], lambda m: "body",
                                verified=False)
    assert "UNVERIFIED" in md.upper()
