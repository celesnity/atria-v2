"""Graph build orchestration: backbone always, extraction cached + toggled."""
from __future__ import annotations

import importlib.util
import json
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


class RecordingStore:
    def __init__(self):
        self.docs, self.chunks, self.extractions = [], [], []

    def upsert_document(self, d):
        self.docs.append(d)

    def upsert_chunk(self, c):
        self.chunks.append(c)

    def upsert_extraction(self, chunk_id, ext):
        self.extractions.append(chunk_id)
        return (0, 0)


def _doc(corpus):
    return corpus.Document(
        doc_id="DOC001", title="Sổ tay", department="COMP", classification="Public",
        owner="COMP", knowledge_space="Company Knowledge", last_updated="2025-02-04",
        language="vi", path="/x/DOC001.md", text="đoạn một. đoạn hai.", tags=("sổ",),
    )


def test_build_backbone_upserts_docs_and_chunks():
    gb = _load("graph_build", "ek_gb_backbone")
    corpus = _load("corpus", "ek_corpus_gb")

    def chunk_fn(doc):
        return [type("C", (), {"chunk_id": "DOC001#0", "doc_id": "DOC001",
                               "text": "đoạn một", "title": "Sổ tay", "department": "COMP",
                               "classification": "Public", "knowledge_space": "Company Knowledge",
                               "citation": "Sổ tay [DOC001] · DOC001#0"})()]

    store = RecordingStore()
    stats = gb.build_backbone(store, [_doc(corpus)], chunk_fn)
    assert stats == {"documents": 1, "chunks": 1}
    assert store.docs[0]["tags"] == ["sổ"]
    assert store.chunks[0]["chunk_id"] == "DOC001#0"


def test_build_extraction_skips_cached_chunks(tmp_path):
    gb = _load("graph_build", "ek_gb_extract")
    corpus = _load("corpus", "ek_corpus_gb2")
    calls = {"n": 0}

    def chunk_fn(doc):
        return [type("C", (), {"chunk_id": "DOC001#0", "text": "đoạn một"})()]

    def chat_fn(messages):
        calls["n"] += 1
        return json.dumps({"entities": [], "relationships": []})

    cache = gb.ExtractionCache(str(tmp_path / "cache.json"))
    store = RecordingStore()
    gb.build_extraction(store, [_doc(corpus)], chunk_fn, chat_fn, cache)
    gb.build_extraction(store, [_doc(corpus)], chunk_fn, chat_fn, cache)  # 2nd run cached
    assert calls["n"] == 1  # LLM called once; second run served from cache
