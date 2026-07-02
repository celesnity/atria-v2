"""Split a Document into chunk records carrying citation anchors.

Uses Chonkie's ``RecursiveChunker`` (structure-aware, no embedding model). Each
chunk keeps its character offsets so a returned passage can be traced back to
the exact span of the source document.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import Document  # type: ignore[import-not-found]

# Default target chunk size in tokens. Override with MC_CHUNK_SIZE to re-index
# with smaller (or larger) chunks — smaller chunks yield tighter citations and
# smaller synthesis prompts; re-run ``reset`` + ``ingest`` after changing it.
_DEFAULT_CHUNK_SIZE = 512


def _chunk_size() -> int:
    """Resolve the chunk size from ``MC_CHUNK_SIZE``, falling back on the default."""
    try:
        value = int(os.environ["MC_CHUNK_SIZE"])
    except (KeyError, TypeError, ValueError):
        return _DEFAULT_CHUNK_SIZE
    return value if value > 0 else _DEFAULT_CHUNK_SIZE


@dataclass(frozen=True)
class ChunkRecord:
    """One chunk plus the metadata needed to cite and filter it."""

    chunk_id: str
    text: str
    start_index: int
    end_index: int
    token_count: int
    doc_type: str
    title: str
    revision: str
    ata_chapter: str
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
    stem = Path(doc.path).stem
    records: list[ChunkRecord] = []
    for i, chunk in enumerate(ch.chunk(doc.text)):
        chunk_id = f"{stem}#{i}"
        records.append(
            ChunkRecord(
                chunk_id=chunk_id,
                text=chunk.text,
                start_index=chunk.start_index,
                end_index=chunk.end_index,
                token_count=chunk.token_count,
                doc_type=doc.doc_type,
                title=doc.title,
                revision=doc.revision,
                ata_chapter=doc.ata_chapter,
                source_path=doc.path,
                citation=f"{doc.doc_type} {doc.title} ({doc.revision}) · {chunk_id}",
            )
        )
    return records
