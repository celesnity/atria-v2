"""Paragraph-packing chunker for ingested documents."""

from __future__ import annotations


def chunk_text(text: str, max_chars: int = 900) -> list[str]:
    """Split on blank lines and greedily pack paragraphs up to max_chars.

    A single paragraph longer than max_chars is kept whole. Returns an empty
    list when the text has no non-blank paragraphs.

    Args:
        text: Source text; paragraphs are delimited by blank lines.
        max_chars: Soft cap on chunk length in characters.

    Returns:
        Chunk strings in original order.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
