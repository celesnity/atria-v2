"""Extract plain text from ingested files (pdf / text / markdown)."""

from __future__ import annotations

import os

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".txt", ".md"})


def parse_file(path: str) -> str:
    """Return the plain-text content of a supported file.

    Args:
        path: Absolute path to a `.pdf`, `.txt`, or `.md` file.

    Returns:
        Extracted UTF-8 text.

    Raises:
        ValueError: The extension is not supported.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext!r}")
    if ext == ".pdf":
        return _parse_pdf(path)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _parse_pdf(path: str) -> str:
    """Extract text from every page of a PDF, joined by blank lines."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)
