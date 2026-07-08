"""Shared data core for the tasco_jarvis_map module.

Normalization spec (NORMATIVE — the dashboard JS mirrors this exactly):
  1. lowercase, trim, collapse internal whitespace;
  2. fold: Vietnamese dj (d-bar) -> d, NFD decompose, strip combining marks;
  3. abbreviation expansion on the folded token stream, longest n-gram first.

All module scripts import from here so Python stays the single source of truth.
Run everything with PYTHONUTF8=1 on Windows.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = MODULE_DIR / "data"

_WS_RE = re.compile(r"\s+")


def fold(text: str) -> str:
    """Lowercase + strip Vietnamese diacritics ('quận' -> 'quan', 'đ' -> 'd')."""
    if not text:
        return ""
    s = str(text).lower().replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return _WS_RE.sub(" ", s).strip()


def load_json(name: str):
    with open(DATA_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def load_abbreviations() -> tuple[dict[str, str], int]:
    """Returns ({folded_term: folded_expansion}, max_ngram)."""
    raw = load_json("abbreviations.json")
    return raw["terms"], raw["max_ngram"]


def expand_abbrev(folded_text: str, terms: dict[str, str], max_ngram: int) -> str:
    """Expand abbreviations in an already-folded string, longest n-gram first.

    'cafe q1' -> 'cafe quan 1'; 'tp hcm' wins over a bare 'tp' match.
    """
    tokens = folded_text.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        matched = False
        for n in range(min(max_ngram, len(tokens) - i), 0, -1):
            gram = " ".join(tokens[i : i + n])
            if gram in terms:
                out.append(terms[gram])
                i += n
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def normalize_query(query: str, terms: dict[str, str], max_ngram: int) -> str:
    """fold + abbreviation expansion — the canonical search key for a user query."""
    return expand_abbrev(fold(query), terms, max_ngram)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def emit(payload: dict) -> None:
    """Print one JSON object to stdout (ASCII-safe — qwen-proof)."""
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
