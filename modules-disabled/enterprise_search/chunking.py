"""Paragraph-packing chunker for small markdown documents."""

from __future__ import annotations


def chunk_markdown(text: str, max_chars: int = 900) -> list[str]:
    """Split on blank lines and greedily pack paragraphs up to max_chars.

    A single paragraph longer than max_chars is kept whole (never split
    mid-sentence); corpus documents are small so this stays bounded.

    Args:
        text: Markdown (or plain) text to chunk. Paragraphs are delimited
            by blank lines ("\\n\\n"); leading/trailing whitespace on each
            paragraph is stripped.
        max_chars: Soft cap on chunk length in characters. Paragraphs are
            packed greedily into a chunk until adding the next paragraph
            would exceed this cap, at which point a new chunk starts. A
            single paragraph longer than max_chars is never split, so an
            individual chunk may exceed the cap.

    Returns:
        A list of chunk strings, each containing one or more paragraphs
        joined by blank lines, in original order. Returns an empty list if
        text has no non-blank paragraphs.
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
