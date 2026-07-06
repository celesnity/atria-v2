"""Tests for persona_schema.extract_personas + validate."""

import importlib.util
import sys
from pathlib import Path

import pytest


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_schema", base / "persona_schema.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _valid_persona():
    return {
        "cluster_id": 0,
        "persona_name": "High-value loyalists",
        "support": 120,
        "support_pct": 0.4,
        "confidence": "HIGH",
        "priority_score": 0.9,
        "is_anomaly": False,
        "segmentation_quality": "NORMAL",
        "risk_tier": "LOW",
        "evidence": {"tenure": 48.0},
        "profile_attributes": {"region": "North"},
        "recommended_actions": ["Upsell premium plan"],
        "sample_persona_text": "Long-tenure, high spend.",
    }


def test_extract_personas_reads_marker_block():
    mod = _load()
    stdout = (
        "noise\n"
        f"{mod.MARKER_START}\n"
        '[{"cluster_id": 0, "persona_name": "x"}]\n'
        f"{mod.MARKER_END}\n"
        "trailing\n"
    )
    got = mod.extract_personas(stdout)
    assert got == [{"cluster_id": 0, "persona_name": "x"}]


def test_extract_personas_returns_none_when_absent():
    mod = _load()
    assert mod.extract_personas("no markers here") is None


def test_extract_personas_returns_none_on_malformed_json():
    mod = _load()
    stdout = f"{mod.MARKER_START}\nnot json\n{mod.MARKER_END}"
    assert mod.extract_personas(stdout) is None


def test_validate_accepts_valid_personas():
    mod = _load()
    mod.validate([_valid_persona()])  # must not raise


def test_validate_rejects_empty_list():
    mod = _load()
    with pytest.raises(ValueError):
        mod.validate([])


def test_validate_rejects_missing_field():
    mod = _load()
    p = _valid_persona()
    del p["priority_score"]
    with pytest.raises(ValueError):
        mod.validate([p])


def test_validate_rejects_bad_support_pct():
    mod = _load()
    p = _valid_persona()
    p["support_pct"] = 1.5
    with pytest.raises(ValueError):
        mod.validate([p])


def test_validate_rejects_bad_confidence():
    mod = _load()
    p = _valid_persona()
    p["confidence"] = "SORT-OF"
    with pytest.raises(ValueError):
        mod.validate([p])


def test_validate_accepts_severity_and_rejects_bad_severity():
    mod = _load()
    good = _valid_persona()
    good["severity"] = "EXTREME"
    mod.validate([good])  # must not raise
    bad = _valid_persona()
    bad["severity"] = "SOMETIMES"
    with pytest.raises(ValueError):
        mod.validate([bad])


def test_validate_rejects_non_dict_profile_attributes():
    mod = _load()
    p = _valid_persona()
    p["profile_attributes"] = ["not", "a", "dict"]
    with pytest.raises(ValueError):
        mod.validate([p])


def test_roadmap_actions_exposed():
    mod = _load()
    assert "Thu thập thêm dữ liệu hành vi" in mod.ROADMAP_ACTIONS
    assert len(mod.ROADMAP_ACTIONS) == 10
