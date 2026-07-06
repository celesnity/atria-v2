"""Tests for persona_sanitize: sentinel scrub, flag reconcile, risk buckets.

Fixtures are lifted from a real production persona dump (the [JSON_START_PERSONA]
sample) so the regressions they lock in are the ones seen in the field.
"""

import importlib.util
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_sanitize", base / "persona_sanitize.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _zero_call_persona():
    # Cluster 4 from the sample: no calls at all, yet flags read 1.0 and the
    # feature means carry 999 / -1 sentinels.
    return {
        "cluster_id": 4,
        "priority_score": 37,
        "risk": "HIGH",
        "risk_tier": "Nhóm rủi ro cao – cần hành động ưu tiên",
        "feature_means": {
            "call_total_6m": 0.0,
            "complaint_total_6m": 0.0032,
            "frequent_caller": 1.0,
            "high_missed_ratio": 1.0,
            "escalating_contact": 0.0,
            "months_since_last_call": 999.0,
            "months_since_last_cl": 641.2486,
            "LOYALTY_POINT": -1.0,
            "VIP_TYPE": -1.0,
            "high_spender": 0.1793,
        },
        "evidence": {
            "call_total_6m": 0.0,
            "frequent_caller": 1.0,
            "high_missed_ratio": 1.0,
            "LOYALTY_POINT": -1.0,
        },
    }


def _high_priority_persona():
    return {"cluster_id": 2, "priority_score": 95, "risk": "HIGH", "feature_means": {}, "evidence": {}}


def _mid_priority_persona():
    return {"cluster_id": 1, "priority_score": 60, "risk": "HIGH", "feature_means": {}, "evidence": {}}


def test_sentinels_scrubbed_from_feature_means_and_evidence():
    mod = _load()
    out = mod.sanitize([_zero_call_persona()])[0]
    fm = out["feature_means"]
    assert "months_since_last_call" not in fm  # 999 sentinel
    assert "LOYALTY_POINT" not in fm and "VIP_TYPE" not in fm  # -1 sentinel
    assert "high_spender" in fm  # real value survives
    assert "LOYALTY_POINT" not in out["evidence"]


def test_call_flags_reconciled_when_no_calls():
    mod = _load()
    out = mod.sanitize([_zero_call_persona()])[0]
    assert out["feature_means"]["frequent_caller"] == 0.0
    assert out["feature_means"]["high_missed_ratio"] == 0.0
    assert out["evidence"]["frequent_caller"] == 0.0


def test_risk_differentiates_by_priority():
    mod = _load()
    high, mid, low = mod.sanitize(
        [_high_priority_persona(), _mid_priority_persona(), _zero_call_persona()]
    )
    assert high["risk"] == "HIGH"  # 95
    assert mid["risk"] == "MEDIUM"  # 60
    assert low["risk"] == "LOW"  # 37
    # No longer every-cluster-HIGH.
    assert {high["risk"], mid["risk"], low["risk"]} == {"HIGH", "MEDIUM", "LOW"}
    assert low["risk_tier"] == mod.RISK_TIER_LOW


def test_input_is_not_mutated():
    mod = _load()
    original = _zero_call_persona()
    mod.sanitize([original])
    # Untouched original still carries the defects.
    assert original["feature_means"]["frequent_caller"] == 1.0
    assert original["feature_means"]["months_since_last_call"] == 999.0
    assert original["risk"] == "HIGH"


def test_nonzero_call_cluster_keeps_flags():
    mod = _load()
    persona = {
        "cluster_id": 1,
        "priority_score": 60,
        "feature_means": {"call_total_6m": 5.79, "frequent_caller": 1.0, "high_missed_ratio": 1.0},
        "evidence": {},
    }
    out = mod.sanitize([persona])[0]
    # A cluster that actually calls keeps its flags.
    assert out["feature_means"]["frequent_caller"] == 1.0
    assert out["feature_means"]["high_missed_ratio"] == 1.0
