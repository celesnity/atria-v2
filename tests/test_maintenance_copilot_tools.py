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


def _mock_pipeline(monkeypatch, answer, citations, confidence, needs_review):
    monkeypatch.setattr(mc_tools.copilot, "_build_store", lambda *a, **k: _FakeStore())
    monkeypatch.setattr(
        mc_tools.copilot,
        "synthesize_answer",
        lambda text, hits: {
            "answer": answer,
            "citations": citations,
            "confidence": confidence,
            "needs_review": needs_review,
            "disclaimer": "ADVISORY ONLY — a licensed engineer must verify and sign off.",
        },
    )


def test_run_query_high_confidence_shapes_payload(monkeypatch):
    _mock_pipeline(monkeypatch, "Use MEL 32-42 [mel_ata32#3]", ["mel_ata32#3"], 0.72, False)
    out = mc_tools.run_query("brake temp MEL relief")
    assert out["answer"].startswith("Use MEL")
    assert out["confidence_band"] == "high"
    assert out["review_required"] is False
    cite = out["citations"][0]
    assert cite["doc"] == "MEL"
    assert cite["revision"] == "Rev-18"
    assert cite["ata"] == "32"
    assert cite["chunk_id"] == "mel_ata32#3"
    assert "ADVISORY" in out["advisory_note"]


def test_run_query_low_confidence_flags_review(monkeypatch):
    _mock_pipeline(monkeypatch, "Insufficient grounded evidence — routed for review.", [], 0.10, True)
    out = mc_tools.run_query("ambiguous question")
    assert out["confidence_band"] == "low"
    assert out["review_required"] is True
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
