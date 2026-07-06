"""Tests for the deterministic semantic gates."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
# gates.py imports `persona_schema` and `verdict` by bare name (matching the
# reference layout, where all these modules live flat in the same scripts
# dir). Put the scripts dir on sys.path so those bare imports resolve, same
# pattern as the sibling test_data_copilot_persona_*.py files.
if str(_MOD) not in sys.path:
    sys.path.insert(0, str(_MOD))


def _load(name: str, sentinel: str):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def _gates():
    _load("verdict", "dc_verdict_g")
    _load("persona_schema", "persona_schema")  # gates imports it by bare name
    return _load("gates", "dc_gates")


def test_non_business_task_short_circuits_accept():
    g = _gates()
    v = g.verify_semantics("print the head of the csv", "df.head()", "ok")
    assert v["status"] == "ACCEPT"


def test_missing_json_block_revises():
    g = _gates()
    code = "from sklearn.cluster import KMeans\nKMeans(n_clusters=3)"
    v = g.verify_semantics("segment customers into personas", code, "no markers here")
    assert v["status"] == "REVISE"
    assert "JSON" in v["feedback"]


def test_priority_score_without_formula_revises():
    g = _gates()
    code = "from sklearn.cluster import KMeans\nKMeans(n_clusters=3)"
    # Three well-formed personas so Rule 3-6 (JSON/K/naming/ARPU) all pass
    # cleanly and Gate 8 (revenue integrity) doesn't fire (arpu > 0), leaving
    # Rule 12 (priority-score-without-formula) as the only gate that trips.
    # Deliberately avoids the letters/symbols Rule 12's own regex treats as
    # "has a formula" (=, *, the letter x) anywhere in the stdout.
    personas = [
        {
            "cluster_id": 0,
            "persona_name": "Persona Frequent Caller",
            "priority_score": 10,
            "evidence": {"f": 1},
            "support": 100,
            "support_pct": 0.3,
            "churn_rate": 0.2,
            "arpu": 100000,
        },
        {
            "cluster_id": 1,
            "persona_name": "Persona Network Complainer",
            "priority_score": 8,
            "evidence": {"f": 1},
            "support": 100,
            "support_pct": 0.3,
            "churn_rate": 0.2,
            "arpu": 100000,
        },
        {
            "cluster_id": 2,
            "persona_name": "Persona Loyal Long Term",
            "priority_score": 5,
            "evidence": {"f": 1},
            "support": 100,
            "support_pct": 0.4,
            "churn_rate": 0.1,
            "arpu": 100000,
        },
    ]
    stdout = (
        "We rank clusters by priority score for outreach and follow up.\n"
        "[JSON_START_PERSONA]" + json.dumps(personas) + "[JSON_END_PERSONA]"
    )
    v = g.verify_semantics("segment customers into personas", code, stdout)
    assert v["status"] == "REVISE"
    assert "Thiếu Minh Bạch" in v["feedback"]


def test_causal_hallucination_revises_telecom():
    g = _gates()
    stdout = (
        "priority_score = a*b\n[JSON_START_PERSONA]"
        '[{"cluster_id":0,"persona_name":"A","priority_score":1,"evidence":{"f":1}}]'
        "[JSON_END_PERSONA]\nchurn do khuyến mãi của đối thủ"
    )
    v = g.verify_semantics("segment", "code", stdout, domain="telecom")
    assert v["status"] == "REVISE"
    assert "khuyến mãi" in v["feedback"] or "Causal" in v["feedback"] or "Nhân Quả" in v["feedback"]


def test_is_business_task_keywords():
    g = _gates()
    assert g.is_business_task("segment customers into personas") is True
    assert g.is_business_task("show me df.shape") is False


def test_verify_syntax_uses_chat_fn():
    g = _gates()

    def fake_chat(messages):
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        return "fix instruction"

    result = g.verify_syntax("bad code", "Traceback...", "do something", fake_chat)
    assert result == "fix instruction"


def test_verify_syntax_falls_back_on_chat_fn_error():
    g = _gates()

    def broken_chat(messages):
        raise RuntimeError("boom")

    result = g.verify_syntax("bad code", "Traceback...", "do something", broken_chat)
    assert "Try using alternative approach" in result
    assert "boom" in result


def test_geography_dominance_revises():
    g = _gates()
    code = "feature_cols = ['a', 'khu_vuc']\nKMeans(n_clusters=3)"
    v = g.verify_semantics("segment customers into personas", code, "khu_vuc info")
    assert v["status"] == "REVISE"
    assert "Geography Dominance" in v["feedback"]


def test_k_less_than_3_revises():
    g = _gates()
    stdout = (
        "[JSON_START_PERSONA]"
        '[{"cluster_id":0,"persona_name":"Persona Alpha","priority_score":1,'
        '"evidence":{"f":1},"support":10,"support_pct":0.5,"churn_rate":0.1},'
        '{"cluster_id":1,"persona_name":"Persona Beta","priority_score":1,'
        '"evidence":{"f":1},"support":10,"support_pct":0.5,"churn_rate":0.1}]'
        "[JSON_END_PERSONA]"
    )
    v = g.verify_semantics("segment customers into personas", "KMeans(n_clusters=2)", stdout)
    assert v["status"] == "REVISE"
    assert "K) phải >= 3" in v["feedback"]
