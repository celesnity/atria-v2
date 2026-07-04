"""Tests for the maintenance_copilot code-bearing skill tool (modules/.../tools.py).

Retrieval + synthesis are mocked, so these run with no Qdrant/Neo4j/LLM.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from atria.core.skill_tools import SkillToolContext

_TOOLS_PATH = Path(__file__).resolve().parents[1] / "modules" / "maintenance_copilot" / "tools.py"


def _load_tools():
    spec = importlib.util.spec_from_file_location("mc_tools_under_test", _TOOLS_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mc_tools = _load_tools()


_HIT = {
    "chunk_id": "mel_ata32#3",
    "doc_type": "MEL",
    "revision": "Rev-18",
    "ata_chapter": "32",
    "citation": "MEL Brakes (Rev-18) · mel_ata32#3",
    "text": "Brake temperature monitoring may be inoperative per MEL ...",
    "score": 0.72,
}


class _FakeStore:
    def query(self, *args, **kwargs):
        return [_HIT]


def _structured(answer, citations, answer_type="synthesized", exact_quote="", sensitive=False):
    return {
        "answer_type": answer_type,
        "response": {"primary_answer": answer, "exact_quote": exact_quote,
                     "is_sensitive": sensitive},
        "citations": [
            {"chunk_id": cid, "source_id": "mel_ata32", "source_name": "mel_ata32.md",
             "source_path": "/x/mel_ata32.md", "page_number": None,
             "confidence_score": 0.72, "char_start": 0, "char_end": 5}
            for cid in citations
        ],
        "related_suggestions": ["What is the dispatch category?"],
        "data_collection_requirement": {
            "needs_user_input": answer_type == "clarification_needed",
            "missing_fields": [],
        },
    }


def _mock_pipeline(monkeypatch, answer, citations, confidence, needs_review, **kw):
    monkeypatch.setattr(mc_tools.copilot, "_build_store", lambda *a, **k: _FakeStore())
    audit_events: list = []
    monkeypatch.setattr(mc_tools.audit, "append_event", lambda e: audit_events.append(e) or e)
    answer_type = kw.pop("answer_type", "clarification_needed" if needs_review else "synthesized")
    monkeypatch.setattr(
        mc_tools.copilot,
        "synthesize_answer",
        lambda text, hits: {
            "structured": _structured(answer, citations, answer_type=answer_type, **kw),
            "answer": answer,
            "answer_type": answer_type,
            "confidence": confidence,
            "needs_review": needs_review,
            "disclaimer": "ADVISORY ONLY — a licensed engineer must verify and sign off.",
            "citations": citations,
            "validation_warnings": [],
            "attempts": 1,
            "json_mode": "schema",
        },
    )
    return audit_events


def test_run_query_high_confidence_shapes_payload(monkeypatch):
    audit_events = _mock_pipeline(
        monkeypatch, "Use MEL 32-42", ["mel_ata32#3"], 0.72, False,
        answer_type="extractive", exact_quote="Brake temperature monitoring",
    )
    out = mc_tools.run_query("brake temp MEL relief")
    assert out["answer"].startswith("Use MEL")
    assert out["answer_type"] == "extractive"
    assert out["exact_quote"] == "Brake temperature monitoring"
    assert out["is_sensitive"] is False
    assert out["related_suggestions"] == ["What is the dispatch category?"]
    assert out["data_collection_requirement"]["needs_user_input"] is False
    assert out["confidence_band"] == "high"
    assert out["review_required"] is False
    cite = out["citations"][0]
    assert cite["doc"] == "MEL"
    assert cite["revision"] == "Rev-18"
    assert cite["ata"] == "32"
    assert cite["chunk_id"] == "mel_ata32#3"
    assert cite["source_name"] == "mel_ata32.md"
    assert cite["confidence_score"] == 0.72
    assert (cite["char_start"], cite["char_end"]) == (0, 5)
    assert "ADVISORY" in out["advisory_note"]
    assert out["structured"]["answer_type"] == "extractive"
    # The web/agent path audits the query.
    assert audit_events and audit_events[0]["answer_type"] == "extractive"


def test_run_query_clarification_flags_review(monkeypatch):
    _mock_pipeline(monkeypatch, "Insufficient grounded evidence — routed for review.",
                   [], 0.10, True)
    out = mc_tools.run_query("ambiguous question")
    assert out["confidence_band"] == "low"
    assert out["review_required"] is True
    assert out["answer_type"] == "clarification_needed"
    assert out["data_collection_requirement"]["needs_user_input"] is True
    assert out["citations"] == []


def test_register_tool_broadcasts_card(monkeypatch):
    _mock_pipeline(monkeypatch, "Use MEL 32-42 [mel_ata32#3]", ["mel_ata32#3"], 0.72, False)
    events = []
    ctx = SkillToolContext()
    ctx.broadcaster = lambda e: events.append(e)

    specs = mc_tools.register(ctx)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "maintenance_copilot_query"

    res = spec.handler(query="brake temp MEL relief")
    assert res["success"] is True
    assert res["output"]["confidence_band"] == "high"
    # A structured card was pushed with the routing type.
    assert events and events[0]["type"] == "maintenance_answer"
    assert events[0]["answer"] == res["output"]["answer"]
    assert events[0]["citations"] == res["output"]["citations"]


def _no_audit(monkeypatch):
    monkeypatch.setattr(mc_tools.audit, "append_event", lambda e: e)


def test_qdrant_down_returns_structured_unavailable_card(monkeypatch):
    _no_audit(monkeypatch)

    def dead_store(*a, **k):
        raise ConnectionError("connection refused: localhost:6333")

    monkeypatch.setattr(mc_tools.copilot, "_build_store", dead_store)
    events = []
    ctx = SkillToolContext()
    ctx.broadcaster = lambda e: events.append(e)

    res = mc_tools.register(ctx)[0].handler(query="brake fault 32-41-01")

    assert res["success"] is True
    out = res["output"]
    assert out["answer_type"] == "clarification_needed"
    assert out["validation_warnings"] == ["service_unavailable:qdrant"]
    assert out["review_required"] is True
    assert out["citations"] == []
    assert out["data_collection_requirement"]["needs_user_input"] is False
    assert "unavailable" in out["answer"]
    assert out["structured"]["answer_type"] == "clarification_needed"
    # The model gets an explicit no-freelancing directive.
    assert "Do NOT read the manual files" in res["_llm_suffix"]
    # The frontend still gets the strict-JSON card.
    assert events and events[0]["type"] == "maintenance_answer"
    assert events[0]["validation_warnings"] == ["service_unavailable:qdrant"]


def test_llm_down_flags_llm_service(monkeypatch):
    _no_audit(monkeypatch)
    monkeypatch.setattr(mc_tools.copilot, "_build_store", lambda *a, **k: _FakeStore())

    def dead_llm(text, hits):
        raise TimeoutError("request to http://localhost:8000/v1 timed out")

    monkeypatch.setattr(mc_tools.copilot, "synthesize_answer", dead_llm)

    res = mc_tools.register(SkillToolContext())[0].handler(query="q")
    assert res["success"] is True
    assert res["output"]["validation_warnings"] == ["service_unavailable:llm"]
    assert "unavailable" in res["_llm_suffix"]


def test_non_connectivity_error_still_fails(monkeypatch):
    _no_audit(monkeypatch)

    def broken_store(*a, **k):
        raise ValueError("bad revision literal")

    monkeypatch.setattr(mc_tools.copilot, "_build_store", broken_store)

    res = mc_tools.register(SkillToolContext())[0].handler(query="q")
    assert res["success"] is False
    assert "query failed" in res["error"]
    assert "_llm_suffix" not in res


def test_register_tool_requires_query(monkeypatch):
    _mock_pipeline(monkeypatch, "x", [], 0.5, False)
    ctx = SkillToolContext()
    spec = mc_tools.register(ctx)[0]
    res = spec.handler(query="   ")
    assert res["success"] is False
    assert "required" in res["error"]


def test_real_loader_discovers_the_tool():
    """The REAL SkillToolLoader over the resolved modules root must find the tool.

    This exercises SKILL.md `tools:` frontmatter discovery + a clean import of
    tools.py through the loader's own import path (not the importlib shortcut
    above). Proves discovery works when cwd is the project root; it cannot assert
    the server's cwd at registry-construction time (see the guide's note — the
    live module list being non-empty confirms that separately).
    """
    from atria.core.modules.registry import resolve_modules_root
    from atria.core.skill_tools import SkillToolLoader

    root = resolve_modules_root()
    specs = SkillToolLoader([root]).discover_and_register(SkillToolContext())
    assert any(s.name == "maintenance_copilot_query" for s in specs)
