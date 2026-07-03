"""Tests for persona_report narrative rendering."""

import importlib.util
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location("dc_persona_report", base / "persona_report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _p(cid, name, score):
    return {
        "cluster_id": cid,
        "persona_name": name,
        "support": 10,
        "support_pct": 0.5,
        "confidence": "HIGH",
        "priority_score": score,
        "is_anomaly": False,
        "segmentation_quality": "NORMAL",
        "risk_tier": "LOW",
        "evidence": {"a": 1.0},
        "profile_attributes": {},
        "recommended_actions": ["do x"],
        "sample_persona_text": "t",
    }


def test_build_messages_ranks_by_priority_desc():
    mod = _load()
    msgs = mod.build_messages([_p(0, "low", 0.1), _p(1, "high", 0.9)], "segment")
    user = msgs[1]["content"]
    assert user.index('"high"') < user.index('"low"')


def test_render_report_returns_model_body_when_verified():
    mod = _load()
    out = mod.render_report([_p(0, "x", 0.5)], "q", lambda m: "# Personas\nbody", verified=True)
    assert out == "# Personas\nbody"


def test_render_report_prepends_unverified_banner():
    mod = _load()
    out = mod.render_report([_p(0, "x", 0.5)], "q", lambda m: "body", verified=False)
    assert "UNVERIFIED" in out
