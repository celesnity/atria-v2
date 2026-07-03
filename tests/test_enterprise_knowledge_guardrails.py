from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("ek_guardrails_uut", _MOD / "guardrails.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ek_guardrails_uut"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_enforce_citations_drops_uncited_sentences():
    g = _load()
    out = g.enforce_citations(
        "Nhân viên có 15 ngày phép [DOC002#0]. Câu này không có trích dẫn.",
        allowed={"DOC002#0"},
    )
    assert "[DOC002#0]" in out["answer"]
    assert "không có trích dẫn" not in out["answer"]
    assert len(out["dropped"]) == 1


def test_needs_review_when_nothing_grounded():
    g = _load()
    assert g.needs_manual_review(0.9, 0) is True


def test_needs_review_when_low_confidence():
    g = _load()
    assert g.needs_manual_review(0.1, 3) is True
    assert g.needs_manual_review(0.9, 3) is False
