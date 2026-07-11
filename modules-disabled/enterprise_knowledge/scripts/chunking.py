"""Split a Document into chunk records carrying citation anchors.

Uses Chonkie's ``RecursiveChunker`` (structure-aware, no embedding model). Each
chunk keeps its character offsets and its document's metadata so a returned
passage traces back to the exact span and its access classification.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import sibling  # noqa: E402

Document = sibling("corpus").Document

_DEFAULT_CHUNK_SIZE = 512


def _chunk_size() -> int:
    """Resolve the chunk size from ``EK_CHUNK_SIZE``, falling back on the default."""
    try:
        value = int(os.environ["EK_CHUNK_SIZE"])
    except (KeyError, TypeError, ValueError):
        return _DEFAULT_CHUNK_SIZE
    return value if value > 0 else _DEFAULT_CHUNK_SIZE


@dataclass(frozen=True)
class ChunkRecord:
    """One chunk plus the metadata needed to cite and access-filter it."""

    doc_id: str
    chunk_id: str
    text: str
    start_index: int
    end_index: int
    token_count: int
    title: str
    department: str
    classification: str
    knowledge_space: str
    owner: str
    source_path: str
    citation: str


def _default_chunker():
    from chonkie import RecursiveChunker  # local import: heavy optional dep

    return RecursiveChunker(chunk_size=_chunk_size())


def chunk_document(doc: Document, chunker: object | None = None) -> list[ChunkRecord]:
    """Chunk ``doc.text`` into citation-anchored records.

    Args:
        doc: The parsed document to split.
        chunker: An object with ``.chunk(text) -> list`` of chunk objects
            exposing ``text``, ``start_index``, ``end_index``, ``token_count``.
            Defaults to a Chonkie ``RecursiveChunker``.

    Returns:
        One :class:`ChunkRecord` per chunk, in document order.
    """
    ch = chunker or _default_chunker()
    records: list[ChunkRecord] = []
    for i, chunk in enumerate(ch.chunk(doc.text)):
        chunk_id = f"{doc.doc_id}#{i}"
        records.append(
            ChunkRecord(
                doc_id=doc.doc_id,
                chunk_id=chunk_id,
                text=chunk.text,
                start_index=chunk.start_index,
                end_index=chunk.end_index,
                token_count=chunk.token_count,
                title=doc.title,
                department=doc.department,
                classification=doc.classification,
                knowledge_space=doc.knowledge_space,
                owner=doc.owner,
                source_path=doc.path,
                citation=f"{doc.title} [{doc.doc_id}] · {chunk_id}",
            )
        )
    return records
