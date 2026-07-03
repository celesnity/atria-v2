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


def test_rich_fields_present_on_every_suggestion():
    charts = _load()
    cols = [{"name": "region", "type": "string"}, {"name": "revenue", "type": "number"}]
    rows = [{"region": "N", "revenue": 10}, {"region": "S", "revenue": 20}]
    sug = charts.detect_suggestions(cols, rows)
    assert sug, "expected at least one suggestion"
    for s in sug:
        assert set(s).issuperset({"chart_type", "x", "y", "title", "description", "labels", "units"})
        assert isinstance(s["description"], str) and s["description"]
        # labels is an identity map keyed by the suggestion's own y series
        assert s["labels"] == {col: col for col in s["y"]}
        assert isinstance(s["units"], dict)


def test_combo_for_dual_magnitude_numeric():
    charts = _load()
    cols = [
        {"name": "month", "type": "string"},
        {"name": "revenue", "type": "number"},
        {"name": "margin_pct", "type": "number"},
    ]
    rows = [
        {"month": "Jan", "revenue": 1_000_000, "margin_pct": 12},
        {"month": "Feb", "revenue": 2_000_000, "margin_pct": 15},
    ]
    sug = charts.detect_suggestions(cols, rows)
    combo = next((s for s in sug if s["chart_type"] == "combo"), None)
    assert combo is not None, "expected a combo suggestion for dual-magnitude columns"
    assert combo["combo"] == {"revenue": "bar", "margin_pct": "line"}
    assert combo["secondaryAxis"] == ["margin_pct"]


def test_no_combo_for_similar_magnitude_numeric():
    charts = _load()
    cols = [
        {"name": "region", "type": "string"},
        {"name": "sales", "type": "number"},
        {"name": "units", "type": "number"},
    ]
    rows = [{"region": "N", "sales": 100, "units": 10}, {"region": "S", "sales": 200, "units": 20}]
    sug = charts.detect_suggestions(cols, rows)
    assert all(s["chart_type"] != "combo" for s in sug)


def test_radar_for_multi_numeric_small_table():
    charts = _load()
    cols = [
        {"name": "segment", "type": "string"},
        {"name": "a", "type": "number"},
        {"name": "b", "type": "number"},
        {"name": "c", "type": "number"},
    ]
    rows = [{"segment": "X", "a": 1, "b": 2, "c": 3}, {"segment": "Y", "a": 3, "b": 2, "c": 1}]
    sug = charts.detect_suggestions(cols, rows)
    radar = next((s for s in sug if s["chart_type"] == "radar"), None)
    assert radar is not None
    assert radar["normalized"] is False
