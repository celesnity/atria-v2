"""Tests for strict-JSON synthesis: enforcement modes, retries, and guardrails."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "maintenance_copilot" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


_HITS = [
    {"chunk_id": "amm_ata32#1", "text": "Torque the pivot pin nut to 1200 in-lb.",
     "citation": "AMM ... · amm_ata32#1", "score": 0.9,
     "source_path": "/x/amm_ata32.md", "source_id": "amm_ata32",
     "source_name": "amm_ata32.md", "page_number": None},
    {"chunk_id": "mel_ata32#0", "text": "MEL 32-30-01 Category C.",
     "citation": "MEL ... · mel_ata32#0", "score": 0.8,
     "source_path": "/x/mel_ata32.md", "source_id": "mel_ata32",
     "source_name": "mel_ata32.md", "page_number": None},
]

_GOOD_JSON = json.dumps({
    "answer_type": "extractive",
    "response": {
        "primary_answer": "Torque is 1200 in-lb.",
        "exact_quote": "Torque the pivot pin nut to 1200 in-lb.",
        "is_sensitive": False,
    },
    "citations": [{"chunk_id": "amm_ata32#1"}],
    "related_suggestions": ["What is the MEL category?"],
    "data_collection_requirement": {"needs_user_input": False, "missing_fields": []},
})


class _ScriptedChat:
    """A chat_fn that returns scripted responses and records its calls."""

    def __init__(self, responses, raise_on_response_format=False):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.raise_on_response_format = raise_on_response_format

    def __call__(self, messages, **kw):
        self.calls.append({"messages": messages, "kw": kw})
        if self.raise_on_response_format and "response_format" in kw:
            raise RuntimeError("response_format not supported")
        return self.responses.pop(0)


def test_valid_first_attempt(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut")
    monkeypatch.delenv("MC_SYNTHESIS_JSON_MODE", raising=False)
    chat = _ScriptedChat([_GOOD_JSON])
    out = syn.synthesize("gear torque?", _HITS, chat)
    assert out["answer"] == "Torque is 1200 in-lb."
    assert out["answer_type"] == "extractive"
    assert out["citations"] == ["amm_ata32#1"]
    assert out["needs_review"] is False
    assert out["attempts"] == 1
    assert out["validation_warnings"] == []
    assert "ADVISORY ONLY" in out["disclaimer"]
    cit = out["structured"]["citations"][0]
    assert cit["source_name"] == "amm_ata32.md"
    assert cit["confidence_score"] == pytest.approx(0.9)
    assert (cit["char_start"], cit["char_end"]) == (0, 39)


def test_schema_mode_sends_json_schema_and_prompt_mode_does_not(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut2")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "schema")
    chat = _ScriptedChat([_GOOD_JSON])
    out = syn.synthesize("q", _HITS, chat)
    rf = chat.calls[0]["kw"]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"]["properties"]["answer_type"]["enum"]
    assert out["json_mode"] == "schema"

    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "prompt")
    chat = _ScriptedChat([_GOOD_JSON])
    out = syn.synthesize("q", _HITS, chat)
    assert "response_format" not in chat.calls[0]["kw"]
    assert out["json_mode"] == "prompt"


def test_provider_rejection_downgrades_modes(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut3")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "schema")
    chat = _ScriptedChat([_GOOD_JSON], raise_on_response_format=True)
    out = syn.synthesize("q", _HITS, chat)
    assert out["json_mode"] == "prompt"
    assert "json_mode_downgraded:json_object" in out["validation_warnings"]
    assert "json_mode_downgraded:prompt" in out["validation_warnings"]
    assert out["answer_type"] == "extractive"


def test_invalid_then_valid_retries_with_error_feedback(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut4")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "prompt")
    chat = _ScriptedChat(["not json at all", _GOOD_JSON])
    out = syn.synthesize("q", _HITS, chat)
    assert out["attempts"] == 2
    assert out["answer_type"] == "extractive"
    retry_messages = chat.calls[1]["messages"]
    assert retry_messages[-2]["content"] == "not json at all"
    assert "failed validation" in retry_messages[-1]["content"]


def test_all_attempts_invalid_falls_back_to_clarification(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut5")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "prompt")
    chat = _ScriptedChat(["bad", "worse", "still bad"])
    out = syn.synthesize("q", _HITS, chat)
    assert out["attempts"] == 3
    assert out["answer_type"] == "clarification_needed"
    assert out["needs_review"] is True
    assert any(w.startswith("fallback:validation_failed:") for w in out["validation_warnings"])
    assert out["structured"]["data_collection_requirement"]["needs_user_input"] is True


def test_unverifiable_quote_retries_then_falls_back(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut6")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "prompt")
    fixed = json.loads(_GOOD_JSON)
    fixed["response"]["exact_quote"] = "Torque the pivot pin nut to 1200 inch-pounds."
    bad = json.dumps(fixed)
    chat = _ScriptedChat([bad, bad, bad])
    out = syn.synthesize("q", _HITS, chat)
    assert out["answer_type"] == "clarification_needed"
    assert "verbatim substring" in chat.calls[1]["messages"][-1]["content"]


def test_low_confidence_forces_clarification_despite_valid_json(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut7")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "prompt")
    low = [{**_HITS[0], "score": 0.05}]
    chat = _ScriptedChat([_GOOD_JSON])
    out = syn.synthesize("q", low, chat)
    assert out["answer_type"] == "clarification_needed"
    assert out["needs_review"] is True
    assert "manual review" in out["answer"]
    # Evidence retained for the reviewing engineer.
    assert out["citations"] == ["amm_ata32#1"]


def test_sensitivity_backstop_overrides_llm_flag(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut8")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "prompt")
    hits = [{**_HITS[0], "text": "Contractor salary is 100 units. Torque is 1200 in-lb."}]
    data = json.loads(_GOOD_JSON)
    data["response"]["exact_quote"] = "Contractor salary is 100 units."
    data["response"]["is_sensitive"] = False
    chat = _ScriptedChat([json.dumps(data)])
    out = syn.synthesize("q", hits, chat)
    assert out["structured"]["response"]["is_sensitive"] is True


def test_budget_truncates_oversized_top_hit(monkeypatch):
    syn = _load("synthesis", "mc_synth_uut9")
    monkeypatch.setenv("MC_SYNTHESIS_JSON_MODE", "prompt")
    monkeypatch.setenv("MC_MODEL_CTX", "3000")
    huge = {**_HITS[0], "text": "gear " * 4000}
    fitted = syn.fit_hits_to_budget("q", [huge])
    assert len(fitted) == 1
    assert len(fitted[0]["text"]) < len(huge["text"])
    assert fitted[0]["text"].endswith("…[truncated to fit context]")


def test_chunk_blocks_carry_copyable_metadata():
    syn = _load("synthesis", "mc_synth_uut10")
    messages = syn.build_synthesis_messages("q", _HITS)
    user = messages[1]["content"]
    assert "chunk_id: amm_ata32#1" in user
    assert "source_name: mel_ata32.md" in user
    assert user.count("<chunk>") == 2
