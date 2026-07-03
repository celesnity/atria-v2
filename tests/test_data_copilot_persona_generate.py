"""Tests for persona_generate prompt building + code extraction."""

import importlib.util
import sys
from pathlib import Path


def _load():
    base = Path(__file__).resolve().parent.parent / "modules" / "data_copilot" / "scripts"
    sys.path.insert(0, str(base))
    spec = importlib.util.spec_from_file_location(
        "dc_persona_generate", base / "persona_generate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_build_messages_mentions_markers_and_schema():
    mod = _load()
    msgs = mod.build_messages("segment customers", {"path": "d.csv", "columns": []})
    system = msgs[0]["content"]
    assert "[JSON_START_PERSONA]" in system and "[JSON_END_PERSONA]" in system
    assert "persona_name" in system and "priority_score" in system


def test_build_messages_injects_k_and_repair_context():
    mod = _load()
    msgs = mod.build_messages(
        "seg",
        {"path": "d.csv", "columns": []},
        k=4,
        prior_error="Boom",
        hypotheses="add evidence",
    )
    user = msgs[1]["content"]
    assert "4" in user and "Boom" in user and "add evidence" in user


def test_build_messages_telecom_domain_adds_guidance():
    mod = _load()
    base = mod.build_messages("seg", {"path": "d.csv", "columns": []})[0]["content"]
    tele = mod.build_messages("seg", {"path": "d.csv", "columns": []}, domain="telecom")[0][
        "content"
    ]
    assert len(tele) > len(base)


def test_generate_code_extracts_fenced_block():
    mod = _load()
    chat = lambda messages: "text\n```python\nprint('hi')\n```\n"
    code = mod.generate_code("seg", {"path": "d.csv", "columns": []}, chat)
    assert "print('hi')" in code
