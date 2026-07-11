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


_HHMM_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")


def parse_opening_hours(spec: str | None) -> tuple[int, int] | None:
    """Parse an opening_hours string to (open_min, close_min) since midnight.

    Handles the dataset's formats: '24/7' -> (0, 1440); the first 'HH:MM-HH:MM'
    anywhere in the string (so 'Mở cửa 06:00-19:00' works); a close <= open is
    treated as overnight (+1440). Returns None when nothing parses.
    """
    if not spec:
        return None
    s = str(spec).strip().lower()
    if "24/7" in s or "24h" in s or "ca ngay" in s:
        return (0, 1440)
    m = _HHMM_RE.search(s)
    if not m:
        return None
    open_min = int(m.group(1)) * 60 + int(m.group(2))
    close_min = int(m.group(3)) * 60 + int(m.group(4))
    if close_min <= open_min:
        close_min += 1440  # crosses midnight
    return (open_min, close_min)


def is_open_at(spec: str | None, minute_of_day: int) -> bool:
    """Is a place with `spec` open at `minute_of_day` (0..1439)? Unknown -> True
    (never hide a place we cannot schedule)."""
    parsed = parse_opening_hours(spec)
    if parsed is None:
        return True
    open_min, close_min = parsed
    for m in (minute_of_day, minute_of_day + 1440):
        if open_min <= m < close_min:
            return True
    return False


def open_after(spec: str | None, minute_of_day: int) -> bool:
    """Is a place still open AT OR AFTER `minute_of_day` (i.e. closes later than
    the given time)? Used by 'mở cửa sau 10 giờ tối'. Unknown -> True."""
    parsed = parse_opening_hours(spec)
    if parsed is None:
        return True
    _open, close_min = parsed
    return close_min > minute_of_day or close_min >= 1440


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
