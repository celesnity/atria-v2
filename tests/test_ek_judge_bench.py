"""Unit tests for the EK LLM-judge bench pure logic (gates + judge parser).

The bench itself runs live in-container; these lock the scoring logic offline.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _lib():
    spec = importlib.util.spec_from_file_location(
        "ek_bench_lib", REPO / "_local" / "ek_bench" / "bench_lib.py"
    )
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def test_parse_judge_plain_and_fenced():
    L = _lib()
    assert L.parse_judge('{"verdict":"correct","reason":"ok"}')["verdict"] == "correct"
    assert L.parse_judge('```json\n{"verdict":"incorrect","reason":"x"}\n```')["verdict"] == "incorrect"
    assert L.parse_judge('Đây là đánh giá: {"verdict":"leak","reason":"y"} xong')["verdict"] == "leak"
    assert L.parse_judge("garbage")["verdict"] == "error"
    assert L.parse_judge("")["verdict"] == "error"


def test_gates():
    L = _lib()
    assert L.allow_pass(["DOC001"], ["DOC001", "DOC002"], "correct") is True
    assert L.allow_pass(["DOC001"], ["DOC002"], "correct") is False  # no retrieval hit
    assert L.allow_pass(["DOC001"], ["DOC001"], "incorrect") is False  # wrong answer
    assert L.deny_pass("no_leak") is True
    assert L.deny_pass("leak") is False
    assert L.retrieval_hit(["DOC001", "DOC011"], ["DOC011"]) is True  # multi-doc partial


def test_load_doc_texts(tmp_path):
    L = _lib()
    d = tmp_path / "samples"
    d.mkdir()
    (d / "DOC001-x.md").write_text("hello one", encoding="utf-8")
    (d / "DOC011-y.md").write_text("hello eleven", encoding="utf-8")
    out = L.load_doc_texts("DOC001; DOC011", str(d))
    assert set(out) == {"DOC001", "DOC011"}
    assert "eleven" in out["DOC011"]
    assert L.load_doc_texts("DOC999", str(d)) == {}  # missing doc absent
