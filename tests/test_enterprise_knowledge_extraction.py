"""EK graph extraction: JSON parsing, allow-list validation, provenance stamping."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_MOD = Path(__file__).resolve().parent.parent / "modules" / "enterprise_knowledge" / "scripts"


def _load(name, sentinel):
    spec = importlib.util.spec_from_file_location(sentinel, _MOD / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_extraction_keeps_allowed_drops_unknown():
    ex = _load("extraction", "ek_ext_parse")
    raw = json.dumps({
        "entities": [
            {"type": "Policy", "key": "leave_policy", "props": {}},
            {"type": "Bogus", "key": "x", "props": {}},   # dropped: unknown type
            {"type": "Concept", "key": "", "props": {}},   # dropped: empty key
        ],
        "relationships": [
            {"type": "RELATED_TO", "src": "leave_policy", "dst": "hr_handbook",
             "confidence": 0.9},
            {"type": "NOPE", "src": "a", "dst": "b"},       # dropped: unknown type
        ],
    })
    out = ex.parse_extraction(raw, {"source_doc": "DOC001", "page": "DOC001#0"})
    assert [e.key for e in out.entities] == ["leave_policy"]
    assert out.entities[0].props["status"] == "unverified"
    assert out.entities[0].props["source_doc"] == "DOC001"
    assert [(e.src_key, e.dst_key) for e in out.edges] == [("leave_policy", "hr_handbook")]
    assert out.edges[0].props["confidence"] == 0.9


def test_parse_extraction_rejects_non_json():
    ex = _load("extraction", "ek_ext_bad")
    with pytest.raises(ValueError):
        ex.parse_extraction("not json at all", {})


def test_extract_graph_calls_chat_fn_and_parses():
    ex = _load("extraction", "ek_ext_call")
    captured = {}

    def chat_fn(messages):
        captured["messages"] = messages
        return json.dumps({"entities": [{"type": "Concept", "key": "k", "props": {}}],
                           "relationships": []})

    out = ex.extract_graph("Nội dung tiếng Việt", chat_fn, {"source_doc": "DOC002"})
    assert out.entities[0].key == "k"
    assert captured["messages"][0]["role"] == "system"
