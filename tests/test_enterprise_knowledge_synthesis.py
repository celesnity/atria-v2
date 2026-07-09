from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_synthesize_grounds_and_cites():
    _load("budget", "ek_budget_for_synth")
    _load("guardrails", "ek_guardrails_for_synth")
    synthesis = _load("synthesis", "ek_synthesis_uut")
    hits = [{"chunk_id": "DOC002#0", "text": "Nhân viên có 15 ngày phép năm.", "score": 0.9}]

    def fake_chat(messages):
        return "Nhân viên được 15 ngày nghỉ phép năm [DOC002#0]."

    out = synthesis.synthesize("Bao nhiêu ngày phép?", hits, fake_chat)
    assert "[DOC002#0]" in out["answer"]
    assert out["citations"] == ["DOC002#0"]
    assert out["needs_review"] is False


def test_synthesize_flags_review_when_uncited():
    _load("budget", "ek_budget_for_synth2")
    _load("guardrails", "ek_guardrails_for_synth2")
    synthesis = _load("synthesis", "ek_synthesis_uut2")
    hits = [{"chunk_id": "DOC002#0", "text": "x", "score": 0.9}]
    out = synthesis.synthesize("q", hits, lambda m: "Câu trả lời không trích dẫn.")
    assert out["needs_review"] is True
