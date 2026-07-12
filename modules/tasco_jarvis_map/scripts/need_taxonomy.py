"""Controlled *need* vocabulary: user language -> canonical need key, classified
HARD (objective, confirmable from a POI's attributes) or SOFT (subjective, ranked
from description/embedding evidence).

This is a curated ATTRIBUTE vocabulary (allowed by the module rule) layered on top
of the data-derived amenity vocab (`query_intent.build_context`) and
`data/attribute_taxonomy.json`. It contains **no hardcoded POI or place names** —
only generalizable amenity synonyms.

Matching is fold+abbrev-normalized so a need's phrases align across the query, the
taxonomy, and a POI's `q.attrs` (all pass through the same `xf`). A phrase matches
as whole contiguous words (space-padded containment), so "wc" never matches inside
another token and "bai do xe" matches only the full phrase.

  HARD needs eliminate a candidate when not confirmed (graceful: only while it
  wouldn't empty the results — see search.py). SOFT needs only rank.
  Numeric needs (price / stars) are parsed structurally in query_intent, not here,
  because the corpus has no VND price or hotel-star fields — they are proxied onto
  ordinal `price_level` and review `rating` and always labelled approximate.
"""
from __future__ import annotations

import unicodedata

# key -> {class, syn (raw phrases), label_vi, label_en}
# `syn` phrases are written naturally; they are fold+abbrev-normalized at build
# time so "wi-fi" == "wifi" and accents/đ are handled uniformly.
RAW_NEEDS: dict[str, dict] = {
    # ── HARD — objective amenities confirmable from attributes/tags ──
    "wifi": {
        "class": "hard", "label_vi": "wifi", "label_en": "wifi",
        "syn": ["wifi", "wi-fi", "internet", "có mạng", "mạng mạnh"],
    },
    "parking": {
        "class": "hard", "label_vi": "chỗ đậu xe", "label_en": "parking",
        "syn": ["bãi đậu xe", "bãi đỗ xe", "chỗ đậu xe", "chỗ đỗ xe", "chỗ để xe",
                "gửi xe", "giữ xe", "đậu ô tô", "parking", "bãi xe"],
    },
    "pool": {
        "class": "hard", "label_vi": "hồ bơi", "label_en": "pool",
        "syn": ["hồ bơi", "bể bơi", "pool", "swimming pool"],
    },
    "wc": {
        "class": "hard", "label_vi": "nhà vệ sinh", "label_en": "toilet",
        "syn": ["wc", "toilet", "nhà vệ sinh", "restroom"],
    },
    "private_room": {
        "class": "hard", "label_vi": "phòng riêng", "label_en": "private room",
        "syn": ["phòng riêng", "private room", "phòng kín", "phòng vip"],
    },
    "open_24h": {
        "class": "hard", "label_vi": "mở 24/7", "label_en": "open 24/7",
        "syn": ["24/7", "24 7", "24 giờ", "cả ngày", "mở cả ngày", "xuyên đêm"],
    },
    "charging": {
        "class": "hard", "label_vi": "trạm sạc", "label_en": "ev charging",
        "syn": ["trạm sạc", "sạc điện", "sạc xe điện", "sạc nhanh", "charging"],
    },
    # ── SOFT — subjective / descriptive qualities, ranked from evidence ──
    "near_sea": {
        "class": "soft", "label_vi": "gần biển", "label_en": "near the sea",
        "syn": ["gần biển", "sát biển", "ven biển", "cạnh biển"],
    },
    "family": {
        "class": "soft", "label_vi": "phù hợp gia đình", "label_en": "family friendly",
        "syn": ["phù hợp gia đình", "cho gia đình", "trẻ em", "trẻ nhỏ",
                "family", "kid friendly"],
    },
    "quiet": {
        "class": "soft", "label_vi": "yên tĩnh", "label_en": "quiet",
        "syn": ["yên tĩnh", "không ồn", "tĩnh lặng", "quiet"],
    },
    "view": {
        "class": "soft", "label_vi": "view đẹp", "label_en": "nice view",
        "syn": ["view đẹp", "view biển", "view sông", "view thành phố",
                "cảnh đẹp", "view"],
    },
    "romantic": {
        "class": "soft", "label_vi": "lãng mạn", "label_en": "romantic",
        "syn": ["lãng mạn", "hẹn hò", "romantic", "cặp đôi", "couple"],
    },
    "work_friendly": {
        "class": "soft", "label_vi": "phù hợp làm việc", "label_en": "work friendly",
        "syn": ["phù hợp làm việc", "làm việc", "học tập", "ổ cắm", "workspace",
                "work-friendly"],
    },
    "checkin": {
        "class": "soft", "label_vi": "check-in đẹp", "label_en": "photogenic",
        "syn": ["check-in", "chụp ảnh", "chụp hình", "sống ảo"],
    },
    "late_night": {
        "class": "soft", "label_vi": "mở khuya", "label_en": "open late",
        "syn": ["mở khuya", "mở cửa khuya", "late night"],
    },
    "clean": {
        "class": "soft", "label_vi": "sạch sẽ", "label_en": "clean",
        "syn": ["sạch sẽ", "sạch", "clean"],
    },
    "spacious": {
        "class": "soft", "label_vi": "rộng rãi", "label_en": "spacious",
        "syn": ["rộng rãi", "thoáng", "spacious"],
    },
}

HARD_KEYS = frozenset(k for k, v in RAW_NEEDS.items() if v["class"] == "hard")
SOFT_KEYS = frozenset(k for k, v in RAW_NEEDS.items() if v["class"] == "soft")


def build_need_index(xf) -> dict:
    """Fold+expand every synonym once. `xf(text)->folded` must be the SAME
    normalizer used for the query and a POI's q.attrs (fold + expand_abbrev), so
    all three align. Returns key -> {class, label_vi, label_en, phrases:[folded]}.
    """
    index: dict = {}
    for key, spec in RAW_NEEDS.items():
        phrases = []
        for s in spec["syn"]:
            fs = xf(s)
            if fs and fs not in phrases:
                phrases.append(fs)
        index[key] = {
            "class": spec["class"],
            "label_vi": spec["label_vi"],
            "label_en": spec["label_en"],
            "phrases": phrases,
        }
    return index


def _contains(phrase: str, folded_text: str) -> bool:
    """Whole-word containment on space-padded folded text."""
    if not phrase or not folded_text:
        return False
    return f" {phrase} " in f" {folded_text} "


def match_need(need_key: str, folded_text: str, index: dict) -> str | None:
    """Return the folded phrase that matched `need_key` in `folded_text`, else None."""
    spec = index.get(need_key)
    if not spec:
        return None
    for ph in spec["phrases"]:
        if _contains(ph, folded_text):
            return ph
    return None


def _simple_norm(s: str) -> str:
    """Independent lightweight normalizer for RAW-attribute verification.

    Deliberately NOT the pipeline's fold+expand_abbrev: lowercases, maps đ→d, and
    strips combining accents via NFD. This gives eval/tests a confirmation check
    that does NOT reuse `match_need` on a POI's pre-built `q.attrs`, so an
    abbrev-expansion false positive in the search path would actually surface as a
    disagreement (rather than being tautologically confirmed by the same call)."""
    s = s.lower().replace("đ", "d").replace("Đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def confirms_raw(need_key: str, attributes, tags) -> bool:
    """Independent check: does a need's RAW synonym literally occur in a POI's raw
    `attributes`/`tags` lists? Uses `_simple_norm` (no abbrev expansion) so it is a
    distinct code path from the search-side `match_need(q.attrs)`."""
    blob = _simple_norm(" ".join(list(attributes or []) + list(tags or [])))
    padded = f" {blob} "
    for syn in RAW_NEEDS.get(need_key, {}).get("syn", []):
        ph = _simple_norm(syn)
        if ph and (f" {ph} " in padded or ph in blob):
            return True
    return False


def detect_needs(folded_query: str, index: dict) -> list[dict]:
    """Find every taxonomy need named in a folded+expanded query.
    Returns [{key, class, phrase, label_vi, label_en}], longest-phrase-first so a
    specific need wins display order. Order-stable, de-duplicated by key."""
    hits: list[dict] = []
    seen: set[str] = set()
    for key, spec in index.items():
        ph = match_need(key, folded_query, index)
        if ph and key not in seen:
            seen.add(key)
            hits.append({"key": key, "class": spec["class"], "phrase": ph,
                         "label_vi": spec["label_vi"], "label_en": spec["label_en"]})
    hits.sort(key=lambda h: -len(h["phrase"]))
    return hits
