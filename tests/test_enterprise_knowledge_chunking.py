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


class _FakeChunk:
    def __init__(self, text, start, end):
        self.text, self.start_index, self.end_index = text, start, end
        self.token_count = len(text.split())


class _FakeChunker:
    def chunk(self, text):
        return [_FakeChunk("part one", 0, 8), _FakeChunk("part two", 9, 17)]


def test_chunk_document_builds_citation_anchored_records():
    corpus = _load("corpus", "ek_corpus_for_chunk")
    chunking = _load("chunking", "ek_chunking_uut")
    doc = corpus.Document(
        doc_id="DOC007", title="Khung lương tham khảo", department="HR",
        classification="Confidential", owner="HR",
        knowledge_space="Department Knowledge", last_updated="2025-08-22",
        language="vi", path="/x/DOC007.md", text="part one part two",
    )
    recs = chunking.chunk_document(doc, chunker=_FakeChunker())
    assert [r.chunk_id for r in recs] == ["DOC007#0", "DOC007#1"]
    assert recs[0].classification == "Confidential"
    assert recs[0].department == "HR"
    assert recs[0].citation == "Khung lương tham khảo [DOC007] · DOC007#0"
