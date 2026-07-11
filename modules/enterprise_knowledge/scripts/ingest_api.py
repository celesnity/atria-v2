"""Single-document ingest entry for external callers (e.g. ai_workspace).

Deliberately slim and audit-free so it can be imported in-process without the
full CLI: it pulls in only ``chunk_document`` + ``IndexStore`` and never imports
``audit`` (a module name shared with ai_workspace) or ``knowledge``.

avgdl is a running corpus average derived from the collection's stored
``token_count`` plus the incoming document's chunks — no side table.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import Document, knowledge_space_for  # type: ignore[import-not-found]
from chunking import chunk_document  # type: ignore[import-not-found]
from index_store import IndexStore  # type: ignore[import-not-found]

EMBED_DIM = 1536


def _build_store() -> IndexStore:
    """Build the production IndexStore (Qdrant + ``index_embed`` embedder)."""
    from qdrant_client import QdrantClient
    from config import load_config  # type: ignore[import-not-found]
    from client import RoleClient  # type: ignore[import-not-found]

    q = QdrantClient(
        url=os.environ.get("EK_QDRANT_URL", "http://localhost:6333"),
        api_key=os.environ.get("EK_QDRANT_API_KEY") or None,
    )
    rc = RoleClient(load_config())
    store = IndexStore(q, lambda texts: rc.embed("index_embed", texts))
    store.ensure_collection(dim=int(os.environ.get("EK_EMBED_DIM", str(EMBED_DIM))))
    return store


def _to_document(
    doc_id: str,
    title: str,
    department: str,
    classification: str,
    text: str,
    owner: str,
    knowledge_space: str | None,
) -> Document:
    return Document(
        doc_id=doc_id,
        title=title,
        department=department,
        classification=classification,
        owner=owner or department,
        knowledge_space=knowledge_space or knowledge_space_for(department),
        last_updated="",
        language="vi",
        path=f"aiw://{doc_id}",
        text=text,
        tags=(),
    )


def ingest_document(
    doc_id: str,
    title: str,
    department: str,
    classification: str,
    text: str,
    owner: str = "",
    knowledge_space: str | None = None,
    store: IndexStore | None = None,
) -> dict:
    """Chunk, embed, and upsert one document; return ingest stats.

    Empty/whitespace text indexes nothing. Returns
    ``{"chunks_indexed", "doc_tokens", "avgdl_used"}``.
    """
    if not text or not text.strip():
        return {"chunks_indexed": 0, "doc_tokens": 0, "avgdl_used": 0.0}
    doc = _to_document(doc_id, title, department, classification, text, owner, knowledge_space)
    records = chunk_document(doc)
    store = store or _build_store()
    total_tokens, total_chunks = store.corpus_token_stats()
    doc_tokens = sum(r.token_count for r in records)
    denom = total_chunks + len(records)
    avgdl = (total_tokens + doc_tokens) / denom if denom else 1.0
    n = store.upsert_chunks(records, avgdl=avgdl)
    return {"chunks_indexed": n, "doc_tokens": doc_tokens, "avgdl_used": avgdl}


def remove_document(doc_id: str, store: IndexStore | None = None) -> int:
    """Delete every chunk for ``doc_id`` from the index. Returns count removed."""
    store = store or _build_store()
    return store.delete_by_doc_id(doc_id)


def reindex_documents(docs: list[dict], store: IndexStore | None = None) -> dict:
    """Rebuild the index from ``docs`` with an exact corpus-wide avgdl.

    Each dict carries ``doc_id, title, department, classification, text`` and an
    optional ``owner``. Existing chunks for those doc_ids are removed first.
    """
    import bm25  # type: ignore[import-not-found]

    store = store or _build_store()
    all_records: list = []
    for d in docs:
        if not d.get("text", "").strip():
            continue
        doc = _to_document(
            d["doc_id"],
            d["title"],
            d["department"],
            d["classification"],
            d["text"],
            d.get("owner", ""),
            None,
        )
        store.delete_by_doc_id(d["doc_id"])
        all_records.extend(chunk_document(doc))
    if not all_records:
        return {"documents": len(docs), "chunks_indexed": 0, "avgdl_used": 0.0}
    avgdl = bm25.average_length([r.text for r in all_records])
    n = store.upsert_chunks(all_records, avgdl=avgdl)
    return {"documents": len(docs), "chunks_indexed": n, "avgdl_used": avgdl}
