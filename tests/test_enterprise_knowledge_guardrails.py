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


def test_vietnamese_number_not_split_into_fragments():
    """A '.' inside a Vietnamese amount must not fragment the sentence.

    Regression: the sentence splitter broke ``30.000.000`` at each thousands
    separator, so citation-enforcement kept only the fragment carrying the
    marker and dropped the numbers — corrupting any answer with amounts.
    """
    g = _load()
    sent = ("Dải lương cho Software Engineer là từ 30.000.000 đến "
            "70.000.000 VND [DOC007#1].")
    assert g.split_sentences(sent) == [sent]
    out = g.enforce_citations(sent, allowed={"DOC007#1"})
    assert out["dropped"] == []
    assert "30.000.000" in out["answer"] and "70.000.000" in out["answer"]


def test_split_sentences_mixed_terminators_with_numbers():
    g = _load()
    text = "Điều A [D#0]. Ngân sách 8.000.000 đồng [D#1]! Còn lại? Không rõ."
    assert g.split_sentences(text) == [
        "Điều A [D#0].",
        "Ngân sách 8.000.000 đồng [D#1]!",
        "Còn lại?",
        "Không rõ.",
    ]


def test_needs_review_when_nothing_grounded():
    g = _load()
    assert g.needs_manual_review(0.9, 0) is True


def test_needs_review_when_low_confidence():
    g = _load()
    assert g.needs_manual_review(0.1, 3) is True
    assert g.needs_manual_review(0.9, 3) is False
