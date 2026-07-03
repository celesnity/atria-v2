"""Tests for the heuristic chart-suggestion detection."""

import importlib.util
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    spec = importlib.util.spec_from_file_location("dc_charts", base / "charts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_bar_for_category_plus_number():
    charts = _load()
    cols = [{"name": "region", "type": "string"}, {"name": "revenue", "type": "number"}]
    rows = [{"region": "N", "revenue": 10}, {"region": "S", "revenue": 20}]
    sug = charts.detect_suggestions(cols, rows)
    assert sug[0]["chart_type"] == "bar"
    assert sug[0]["x"] == "region" and sug[0]["y"] == ["revenue"]
    assert any(s["chart_type"] == "pie" for s in sug)


def test_line_for_temporal_x():
    charts = _load()
    cols = [{"name": "month", "type": "string"}, {"name": "sales", "type": "number"}]
    rows = [{"month": "Jan", "sales": 1}, {"month": "Feb", "sales": 2}]
    sug = charts.detect_suggestions(cols, rows)
    assert sug[0]["chart_type"] == "line"


def test_empty_when_no_numeric():
    charts = _load()
    cols = [{"name": "a", "type": "string"}, {"name": "b", "type": "string"}]
    assert charts.detect_suggestions(cols, [{"a": "x", "b": "y"}]) == []
