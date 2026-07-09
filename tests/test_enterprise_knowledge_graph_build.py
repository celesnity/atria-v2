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
        doc_id="DOC001",
        title="Sổ tay",
        department="COMP",
        classification="Public",
        owner="COMP",
        knowledge_space="Company Knowledge",
        last_updated="2025-02-04",
        language="vi",
        path="/x/DOC001.md",
        text="đoạn một. đoạn hai.",
        tags=("sổ",),
    )


def test_build_backbone_upserts_docs_and_chunks():
    gb = _load("graph_build", "ek_gb_backbone")
    corpus = _load("corpus", "ek_corpus_gb")

    def chunk_fn(doc):
        return [
            type(
                "C",
                (),
                {
                    "chunk_id": "DOC001#0",
                    "doc_id": "DOC001",
                    "text": "đoạn một",
                    "title": "Sổ tay",
                    "department": "COMP",
                    "classification": "Public",
                    "knowledge_space": "Company Knowledge",
                    "citation": "Sổ tay [DOC001] · DOC001#0",
                },
            )()
        ]

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
        return [type("C", (), {"chunk_id": "DOC001#0", "doc_id": "DOC001", "text": "đoạn một"})()]

    def chat_fn(messages):
        calls["n"] += 1
        return json.dumps({"entities": [], "relationships": []})

    cache_path = str(tmp_path / "cache.json")
    store = RecordingStore()
    gb.build_extraction(store, [_doc(corpus)], chunk_fn, chat_fn, gb.ExtractionCache(cache_path))
    # 2nd run uses a freshly constructed cache instance to prove the on-disk
    # JSON sidecar (not just the in-memory dict) is honored across processes.
    gb.build_extraction(store, [_doc(corpus)], chunk_fn, chat_fn, gb.ExtractionCache(cache_path))
    assert calls["n"] == 1  # LLM called once; second run served from disk cache


def test_build_extraction_skips_failed_chunks_and_continues(tmp_path):
    """A chunk whose extraction fails is skipped (not cached), the rest proceed."""
    gb = _load("graph_build", "ek_gb_resilient")
    corpus = _load("corpus", "ek_corpus_gb3")

    def chunk_fn(doc):
        mk = lambda i, t: type(  # noqa: E731
            "C", (), {"chunk_id": f"DOC001#{i}", "doc_id": "DOC001", "text": t}
        )()
        return [mk(0, "chunk hỏng"), mk(1, "chunk tốt")]

    def chat_fn(messages):
        if "chunk hỏng" in messages[-1]["content"]:
            return ""  # empty LLM reply -> parse_extraction raises ValueError
        return json.dumps({"entities": [], "relationships": []})

    cache_path = str(tmp_path / "cache.json")
    store = RecordingStore()
    stats = gb.build_extraction(
        store, [_doc(corpus)], chunk_fn, chat_fn, gb.ExtractionCache(cache_path)
    )
    assert stats == {"chunks": 2, "llm_calls": 1, "failed": 1}
    assert store.extractions == ["DOC001#1"]  # good chunk upserted, bad one skipped
    # failed chunk is NOT cached, so a re-run retries it (and succeeds this time)
    calls = {"n": 0}

    def chat_fn_fixed(messages):
        calls["n"] += 1
        return json.dumps({"entities": [], "relationships": []})

    stats2 = gb.build_extraction(
        store, [_doc(corpus)], chunk_fn, chat_fn_fixed, gb.ExtractionCache(cache_path)
    )
    assert stats2["failed"] == 0 and calls["n"] == 1  # only the failed chunk retried
