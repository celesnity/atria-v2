"""Tests for persona_verify deterministic rules."""

import importlib.util
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_verify", base / "persona_verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _persona(**over):
    base = {
        "cluster_id": 0,
        "persona_name": "x",
        "support": 10,
        "support_pct": 0.5,
        "confidence": "HIGH",
        "priority_score": 0.5,
        "is_anomaly": False,
        "segmentation_quality": "NORMAL",
        "risk_tier": "LOW",
        "evidence": {"tenure": 12.0},
        "profile_attributes": {},
        "recommended_actions": ["a"],
        "sample_persona_text": "t",
    }
    base.update(over)
    return base


def test_revise_when_no_persona_block():
    mod = _load()
    verdict = mod.verify_personas("q", "code", "no markers", None)
    assert verdict["status"] == "REVISE"
    assert "JSON" in verdict["hypotheses"]


def test_revise_when_priority_score_has_no_formula():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]"  # block present, but...
    verdict = mod.verify_personas("q", "code has no formula", stdout, [_persona()])
    assert verdict["status"] == "REVISE"
    assert "formula" in verdict["hypotheses"].lower() or "score" in verdict["hypotheses"].lower()


def test_ok_when_formula_present_and_evidence_ok():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]\npriority_score = revenue * churn_rate"
    verdict = mod.verify_personas(
        "q", "priority_score = revenue * churn_rate", stdout, [_persona()]
    )
    assert verdict["status"] == "OK"


def test_revise_when_evidence_empty():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]\nscore = a * b"
    verdict = mod.verify_personas("q", "score = a * b", stdout, [_persona(evidence={})])
    assert verdict["status"] == "REVISE"


def test_anomaly_gate_warns_on_tiny_cluster():
    mod = _load()
    warnings = mod.check_anomaly_gate([_persona(support_pct=0.005, is_anomaly=False)])
    assert warnings and "anomaly" in warnings[0].lower()


def test_load_domain_pack_telecom_returns_rules():
    mod = _load()
    assert len(mod.load_domain_pack("telecom")) >= 1
    assert mod.load_domain_pack("unknown") == []


def test_telecom_pack_flags_causal_hallucination():
    mod = _load()
    stdout = "[JSON_START_PERSONA][JSON_END_PERSONA]\nscore = a*b\nNguyên nhân rời mạng do khuyến mãi"
    verdict = mod.verify_personas("q", "score=a*b", stdout, [_persona()], domain="telecom")
    assert verdict["status"] == "REVISE"
