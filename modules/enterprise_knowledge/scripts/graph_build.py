"""Build the EK knowledge graph from the corpus.

Two passes: a deterministic backbone (Document/Chunk/Tag/Department nodes and
their structural edges — no LLM), and an optional LLM extraction pass that adds
Entity/MENTIONS/RELATED_TO. Extraction is cached by chunk-content hash so a
rebuild re-upserts from cache without re-calling the (rate-limited) LLM.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extraction  # type: ignore[import-not-found]


def doc_to_node(doc) -> dict:
    """Project a ``corpus.Document`` into the node dict ``upsert_document`` wants."""
    return {
        "doc_id": doc.doc_id, "title": doc.title, "department": doc.department,
        "classification": doc.classification, "owner": doc.owner,
        "knowledge_space": doc.knowledge_space, "last_updated": doc.last_updated,
        "tags": list(doc.tags),
    }


def chunk_to_node(rec) -> dict:
    """Project a ``chunking.ChunkRecord`` into the node dict ``upsert_chunk`` wants."""
    return {
        "chunk_id": rec.chunk_id, "doc_id": rec.doc_id, "text": rec.text,
        "title": rec.title, "department": rec.department,
        "classification": rec.classification,
        "knowledge_space": getattr(rec, "knowledge_space", ""), "citation": rec.citation,
    }


class ExtractionCache:
    """A JSON sidecar mapping chunk-content hash -> serialized GraphExtraction."""

    def __init__(self, path: str):
        self._path = Path(path)
        self._data: dict = {}
        if self._path.is_file():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    @staticmethod
    def key(text: str) -> str:
        """Stable content hash for a chunk's text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str):
        """Return a cached ``GraphExtraction`` for ``text`` or ``None``."""
        item = self._data.get(self.key(text))
        if item is None:
            return None
        return extraction.GraphExtraction(
            entities=[extraction.Entity(**e) for e in item["entities"]],
            edges=[extraction.Edge(**x) for x in item["edges"]],
        )

    def put(self, text: str, ext) -> None:
        """Cache ``ext`` for ``text`` and flush to disk."""
        self._data[self.key(text)] = {
            "entities": [{"type": e.type, "key": e.key, "props": e.props}
                         for e in ext.entities],
            "edges": [{"type": x.type, "src_key": x.src_key, "dst_key": x.dst_key,
                       "props": x.props} for x in ext.edges],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")


def build_backbone(store, docs, chunk_fn: Callable) -> dict:
    """Upsert Document/Chunk/Tag/Department nodes and structural edges (no LLM)."""
    n_docs = n_chunks = 0
    for doc in docs:
        store.upsert_document(doc_to_node(doc))
        n_docs += 1
        for rec in chunk_fn(doc):
            store.upsert_chunk(chunk_to_node(rec))
            n_chunks += 1
    return {"documents": n_docs, "chunks": n_chunks}


def build_extraction(store, docs, chunk_fn: Callable, chat_fn: Callable,
                     cache: ExtractionCache) -> dict:
    """Extract Entity/RELATED_TO per chunk (LLM), cached by content hash."""
    n_chunks = n_llm = 0
    for doc in docs:
        for rec in chunk_fn(doc):
            n_chunks += 1
            ext = cache.get(rec.text)
            if ext is None:
                ext = extraction.extract_graph(
                    rec.text, chat_fn,
                    {"source_doc": getattr(rec, "doc_id", ""), "page": rec.chunk_id}
                )
                cache.put(rec.text, ext)
                n_llm += 1
            store.upsert_extraction(rec.chunk_id, ext)
    return {"chunks": n_chunks, "llm_calls": n_llm}
