"""Vietnamese-aware text normalization for lexical search.

Postgres has no Vietnamese FTS dictionary, so we normalize text in Python
(strip diacritics, lowercase, collapse whitespace) and index the normalized
form with the 'simple' tsvector config. Queries are normalized the same way,
which makes diacritic-less input ("ca phe") match diacritic text ("cà phê").
"""

from __future__ import annotations

import re
import unicodedata

_WS_RE = re.compile(r"\s+")


def strip_diacritics(text: str) -> str:
    """Remove combining marks and map đ/Đ to d/D."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D")


def normalize_for_search(text: str) -> str:
    """Lowercased, diacritics-stripped, whitespace-collapsed form for FTS."""
    return _WS_RE.sub(" ", strip_diacritics(text).lower()).strip()
