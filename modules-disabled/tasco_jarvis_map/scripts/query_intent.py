"""Query-intent router for tasco_jarvis_map — pure language-level parsing.

`parse(query, ctx)` turns a raw Vietnamese/English map query into a structured
`Parsed` dict shared by both search engines and jarvis_chat. It answers the 9
competition archetypes (POI / Category / Brand / Address / Nearby / Navigation /
Natural-language / Ambiguous / Coordinate) by extracting, in a NORMATIVE order:

  1. whole-query coordinates       ("10.7769,106.7009")
  2. intent SENTINELS pre-expansion — nav ("chi duong", "duong di") and nearby
     ("gan day", "gan nhat") terms are DERIVED from abbreviations.json values
     (see build_context): the ingest maps them to the literal strings
     "navigation" / "nearby search", so expanding first would leak that English
     into the normalized query. We detect the intent and strip the trigger
     BEFORE expansion. No sentinel word is hardcoded — only literal fallbacks
     for spellings absent from the dictionary.
  3. opening-hours / time constraints ("sau 10 gio toi", "con mo cua", "24/7")
  4. abbreviation expansion + data-derived city detection (gazetteer)
  5. proximity split on connectors ("gan", "near", "quanh", "canh"...): the
     right side is the anchor (landmark / address / coordinate) or a here-word
     (current location). The split is TENTATIVE — search reverts to a plain
     full-query search if the anchor cannot be resolved and is not a here-word.
  6. category + brand detection on the TARGET (left) side only, so an anchor
     like "san bay" never hijacks category detection away from "atm".
  7. address shape (house-number + street validated against the street set).

Place knowledge stays entirely in gazetteer.py; brands and streets are derived
here from the dataset at load (build_context) — nothing about specific cities,
brands or streets is hardcoded, so new data flows through with zero code edits.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gazetteer  # noqa: E402
from _data import expand_abbrev, fold, load_abbreviations, load_json  # noqa: E402

# --- Language-level constants (like fold()'s d-bar->d — NOT place/brand data) ---

# Proximity connectors, longest first for boundary scanning.
CONNECTORS = ("xung quanh", "ben canh", "ke ben", "quanh", "gan", "near", "canh", "sat", "quanh khu")
# "I am here" phrases: proximity to the user's current viewport, no anchor.
HERE_WORDS = frozenset({"day", "toi", "minh", "here", "me", "quanh day", "day nay", "hien tai"})
# Navigation prepositions that head a destination when they lead the remainder.
NAV_PREPS = ("di den", "di toi", "den", "toi", "ve", "di")
# Literal navigation triggers absent from the abbreviation dictionary.
NAV_LITERALS = ("direction", "route", "navigate", "duong di", "duong toi")
# Literal nearby triggers absent from the dictionary.
NEARBY_LITERALS = ("near me", "nearby", "quanh day", "gan toi", "gan minh")
# Generic place-noun heads that must NOT seed a brand family (a brand like
# "Nha thuoc Long Chau" would otherwise let bare "nha thuoc" match the brand).
GENERIC_BRAND_HEADS = frozenset({
    "nha", "quan", "cua", "tram", "tiem", "hang", "cho", "sieu", "trung",
    "benh", "cay", "rap", "ben", "diem", "phong", "the", "cong", "khach",
})
# Generic leading nouns stripped from a brand name to expose its distinctive
# tail ("nha thuoc long chau" -> "long chau"), so a category-word prefix shared
# with a category ("nha thuoc" = pharmacy) does not hide the brand.
GENERIC_LEADING = frozenset({
    "nha", "thuoc", "quan", "cua", "hang", "tiem", "cay", "xang", "tram",
    "benh", "vien", "rap", "chieu", "phim", "ben", "xe", "sieu", "thi",
    "trung", "tam", "thuong", "mai", "cong", "ty", "khach", "san", "ca", "phe",
})

COORD_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d{1,8})?)\s*[,;]\s*(-?\d{1,3}(?:\.\d{1,8})?)\s*$")
COORD_EMBED_RE = re.compile(r"(-?\d{1,2}\.\d{2,8})\s*[,;]\s*(-?\d{1,3}\.\d{2,8})")
# Robust coordinate forms (both numbers must carry a decimal point so plain
# thousands like "1,000" never match). Order-agnostic: lat/lng swap is corrected
# downstream in _mk_coord. Longest/most-specific patterns are tried first.
COORD_LABELED_RE = re.compile(
    r"lat(?:itude)?\s*[:=]?\s*(-?\d{1,3}\.\d{1,8})\D+?"
    r"(?:lng|lon|long|longitude)\s*[:=]?\s*(-?\d{1,3}\.\d{1,8})"
)
COORD_DMS_RE = re.compile(
    r"(\d{1,3})\s*[°:\s]\s*(\d{1,2})\s*['′:\s]\s*(\d{1,2}(?:\.\d+)?)\s*[\"″]?\s*([nsew])"
    r"\D+?"
    r"(\d{1,3})\s*[°:\s]\s*(\d{1,2})\s*['′:\s]\s*(\d{1,2}(?:\.\d+)?)\s*[\"″]?\s*([nsew])"
)
COORD_DECIMAL_RE = re.compile(r"(-?\d{1,3}\.\d{1,8})\s*[,;]\s*(-?\d{1,3}\.\d{1,8})")
COORD_SPACE_RE = re.compile(r"(?<![\d.])(-?\d{1,3}\.\d{1,8})\s+(-?\d{1,3}\.\d{1,8})(?![\d.])")
# "what is here / reverse geocode" cues, and "coordinates of <POI>" lookup cue.
REVERSE_CUE_RE = re.compile(
    r"\b(cho nao|o dau|dia chi|vi tri nao|noi nao|la gi|la dau|o vi tri|"
    r"where is|what.*here|reverse geocode)\b"
)
COORD_LOOKUP_RE = re.compile(
    r"^(?:toa do|vi tri|kinh do vi do|lat[- ]?lng|gps)(?:\s+gps)?\s+(?:cua\s+)?(.+?)"
    r"(?:\s+(?:la gi|la bao nhieu|o dau|the nao|nhu the nao))?$"
)
ADDR_RE = re.compile(r"^(?:so\s+)?(\d{1,4}[a-z]?)\s+(.+)$")

# Time / opening-hours patterns.
_DAYPART_PM = frozenset({"toi", "dem", "khuya", "chieu", "pm"})
TIME_AFTER_RE = re.compile(r"sau\s+(\d{1,2})(?:\s*(?:gio|h|:(\d{2})))?\s*(sang|trua|chieu|toi|dem|khuya|am|pm)?")
OPEN_NOW_RE = re.compile(r"\b(con|dang)\s+mo(?:\s+cua)?\b|open now|con mo cua")
OPEN_LATE_RE = re.compile(r"mo cua muon|open late|\ban dem\b|ve khuya|khuya")
FULL_DAY_RE = re.compile(r"\b24/7\b|24h|24 gio|ca ngay")


def _norm_val(v: str) -> str:
    return fold(str(v))


def build_context() -> dict:
    """Load + derive everything the router needs, ONCE. Sentinel term-sets are
    derived from abbreviations.json values; brands and streets from the data."""
    terms, max_ngram = load_abbreviations()
    pois_doc = load_json("pois.json")
    pois = pois_doc["pois"]
    addresses = load_json("addresses.json")["addresses"]

    # Sentinels derived from the dictionary's own expansions.
    nav_terms, nearby_terms = set(NAV_LITERALS), set(NEARBY_LITERALS)
    for term, expansion in terms.items():
        val = _norm_val(expansion)
        if "navigation" in val or "chi duong" in val:
            nav_terms.add(_norm_val(term))
        if "nearby" in val:
            nearby_terms.add(_norm_val(term))

    # Brands derived from distinct POI brand values (+ no-accent/no-space forms).
    brand_set: set[str] = set()
    brand_family: dict[str, str] = {}  # variant -> canonical folded brand
    for p in pois:
        b = p.get("brand")
        if not b:
            continue
        fb = fold(b)
        if len(fb) < 2:
            continue
        brand_set.add(fb)
        brand_family[fb] = fb
        head = fb.split()[0]
        if len(head) >= 4 and head not in GENERIC_BRAND_HEADS:
            brand_family.setdefault(head, fb)
        # Distinctive tail: drop leading generic nouns ("nha thuoc long chau"
        # -> "long chau") so a query using the short chain name still matches.
        toks = fb.split()
        i = 0
        while i < len(toks) - 1 and toks[i] in GENERIC_LEADING:
            i += 1
        tail = " ".join(toks[i:])
        if 0 < i and len(tail) >= 3 and tail != fb:
            brand_family.setdefault(tail, fb)

    streets = {fold(a["street"]) for a in addresses if a.get("street")}
    streets |= {fold(p["district"]) for p in pois if p.get("district")}

    gaz = gazetteer.build_from_data()
    return {
        "terms": terms,
        "max_ngram": max_ngram,
        "gaz": gaz,
        "nav_terms": sorted(nav_terms, key=len, reverse=True),
        "nearby_terms": sorted(nearby_terms, key=len, reverse=True),
        "brand_set": brand_set,
        "brand_family": brand_family,
        "streets": streets,
    }


_CTX = None


def context() -> dict:
    global _CTX
    if _CTX is None:
        _CTX = build_context()
    return _CTX


def _strip_phrases(text: str, phrases) -> tuple[str, bool]:
    """Remove any of `phrases` (already longest-first) at token boundaries.
    Returns (cleaned, hit)."""
    padded = f" {text} "
    hit = False
    for ph in phrases:
        token = f" {ph} "
        if token in padded:
            padded = padded.replace(token, " ")
            hit = True
    return padded.strip(), hit


def _extract_time(text: str) -> tuple[str, dict | None]:
    """Pull a time/opening-hours constraint out of `text`. Returns (rest, time)."""
    time: dict | None = None
    rest = text
    m = TIME_AFTER_RE.search(rest)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        daypart = m.group(3)
        if daypart in _DAYPART_PM and hour < 12:
            hour += 12
        time = {"after_min": hour * 60 + minute}
        rest = (rest[: m.start()] + " " + rest[m.end():]).strip()
    if time is None and OPEN_NOW_RE.search(rest):
        time = {"open_now": True}
        rest = OPEN_NOW_RE.sub(" ", rest).strip()
    if time is None and FULL_DAY_RE.search(rest):
        time = {"full_day": True}
        rest = FULL_DAY_RE.sub(" ", rest).strip()
    if time is None and OPEN_LATE_RE.search(rest):
        time = {"open_late": True, "after_min": 21 * 60}
        rest = OPEN_LATE_RE.sub(" ", rest).strip()
    return re.sub(r"\s+", " ", rest).strip(), time


def _coords_in_range(lat: float, lng: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lng <= 180


def _mk_coord(a: float, b: float) -> dict | None:
    """Order-correct and range-gate a numeric pair -> {lat,lng,order_corrected}.
    If the first value can only be a longitude (|.|>90) and the second is a valid
    latitude, the pair was given lng,lat and is swapped."""
    lat, lng, corrected = a, b, False
    if abs(lat) > 90 and abs(lng) <= 90:
        lat, lng, corrected = b, a, True
    if not _coords_in_range(lat, lng):
        return None
    return {"lat": lat, "lng": lng, "order_corrected": corrected}


def _dms_to_deg(d: str, m: str, s: str, hemi: str) -> float:
    deg = float(d) + float(m) / 60.0 + float(s) / 3600.0
    return -deg if hemi in ("s", "w") else deg


def find_coordinates(text: str) -> tuple[dict, str] | None:
    """Find the first coordinate anywhere in `text` (labeled / DMS / decimal-comma /
    space-separated, either lat,lng or lng,lat order). Returns
    ({lat,lng,order_corrected}, text_with_the_coordinate_removed) or None."""
    dms = COORD_DMS_RE.search(text)
    if dms:
        a = _dms_to_deg(dms.group(1), dms.group(2), dms.group(3), dms.group(4))
        b = _dms_to_deg(dms.group(5), dms.group(6), dms.group(7), dms.group(8))
        c = _mk_coord(a, b)
        if c:
            cleaned = (text[: dms.start()] + " " + text[dms.end():]).strip()
            return c, re.sub(r"\s+", " ", cleaned).strip()
    for rx in (COORD_LABELED_RE, COORD_DECIMAL_RE, COORD_SPACE_RE):
        m = rx.search(text)
        if not m:
            continue
        c = _mk_coord(float(m.group(1)), float(m.group(2)))
        if c:
            cleaned = (text[: m.start()] + " " + text[m.end():]).strip()
            return c, re.sub(r"\s+", " ", cleaned).strip()
    return None


def parse_coordinates(text: str) -> dict | None:
    """Public: parse the first coordinate from free text (any supported form),
    returning {lat,lng,order_corrected} or None."""
    hit = find_coordinates(fold(text))
    return hit[0] if hit else None


def _split_proximity(text: str) -> tuple[str, str] | None:
    """Split on the first proximity connector at token boundaries.
    Returns (left_target, right_anchor) or None."""
    padded = f" {text} "
    best = None
    for conn in CONNECTORS:
        token = f" {conn} "
        idx = padded.find(token)
        if idx != -1 and (best is None or idx < best[0]):
            best = (idx, conn)
    if best is None:
        return None
    idx, conn = best
    left = padded[:idx].strip()
    right = padded[idx + len(f" {conn} ") - 1:].strip()
    return left, right


def _detect_brands(text: str, ctx: dict) -> tuple[list[str], str]:
    """Longest-first brand-phrase scan. Returns (canonical_brands, remainder)."""
    padded = f" {text} "
    found: list[str] = []
    for variant in sorted(ctx["brand_family"], key=len, reverse=True):
        token = f" {variant} "
        if token in padded:
            canon = ctx["brand_family"][variant]
            if canon not in found:
                found.append(canon)
            padded = padded.replace(token, " ")
    remainder = re.sub(r"\s+", " ", padded).strip()
    if not found:
        # Space-insensitive fallback: the user split a brand token ("vietcom bank"
        # for "vietcombank", "co op mart" for "co.opmart"). Concatenate short word
        # spans and match against space-collapsed brand variants. Runs ONLY when
        # the normal scan found nothing, so it never changes an existing hit.
        collapsed = {
            v.replace(" ", ""): ctx["brand_family"][v]
            for v in ctx["brand_family"] if len(v.replace(" ", "")) >= 6
        }
        words = remainder.split()
        out: list[str] = []
        i = 0
        while i < len(words):
            hit = None
            for j in range(min(len(words), i + 3), i, -1):
                canon = collapsed.get("".join(words[i:j]))
                if canon:
                    hit = (canon, j)
                    break
            if hit:
                if hit[0] not in found:
                    found.append(hit[0])
                i = hit[1]
            else:
                out.append(words[i])
                i += 1
        if found:
            remainder = " ".join(out)
    return found, remainder


def _detect_address(text: str, ctx: dict) -> dict | None:
    """House-number + street shape, street validated against the data streets."""
    m = ADDR_RE.match(text)
    if not m:
        return None
    house, rest = m.group(1), m.group(2).strip()
    street = None
    for s in sorted(ctx["streets"], key=len, reverse=True):
        if s and (rest == s or rest.startswith(s + " ") or f" {s} " in f" {rest} "):
            street = s
            break
    if street is None:
        return None
    return {"house_number": house, "street": street, "rest": rest}


def competition_intent(parsed: dict) -> str:
    """Map the internal intent to a competition acceptance label."""
    intent = parsed["intent"]
    if intent in ("coordinate", "reverse_geocode"):
        return "Coordinate Search"
    if intent == "navigation":
        return "Navigation"
    if intent == "nearby":
        return "Nearby Search"
    if intent == "address":
        return "Address Search"
    if intent == "brand_category":
        return "Brand Category Search"
    if intent == "discovery":
        return "Discovery Search"
    if intent == "category":
        return "Category Search"
    if intent == "ambiguous":
        return "Ambiguous"
    return "POI Search"


def parse(query: str, ctx: dict, detect_category=None, cat_idx=None) -> dict:
    """Parse `query` into a Parsed dict. `detect_category`/`cat_idx` are injected
    from search.py to avoid a circular import; when absent, category stays None."""
    gaz = ctx["gaz"]
    terms, max_ngram = ctx["terms"], ctx["max_ngram"]
    folded = fold(query)
    entities: dict = {}

    parsed = {
        "intent": "poi",
        "query": query,
        "normalized_query": "",
        "target_text": "",
        "name_query": "",
        "category": None,
        "brands": [],
        "remainder": "",
        "anchor_text": None,
        "anchor_coords": None,
        "coords": None,
        "address": None,
        "time": None,
        "city_entry": None,
        "nav": False,
        "nearby": False,
        "destination_text": None,
        "origin_text": None,
        "entities": entities,
        "ambiguous_hint": False,
    }

    # 1. Coordinates anywhere in the query (leading / trailing / embedded, and
    #    lat,lng OR lng,lat — the parser range-gates and swap-corrects).
    forced_anchor_coords = None
    reverse_cue = False
    coord_hit = find_coordinates(folded)
    if coord_hit:
        c, rest = coord_hit
        parsed["coords"] = (c["lat"], c["lng"])
        entities["latitude"], entities["longitude"] = c["lat"], c["lng"]
        if c["order_corrected"]:
            entities["coordinate_order_corrected"] = True
        reverse_cue = bool(REVERSE_CUE_RE.search(rest))
        if reverse_cue:
            # Drop the "what is here" phrase so its tokens (e.g. "cho" in "cho nao"
            # colliding with the market category) don't leak into category/name.
            rest = re.sub(r"\s+", " ", REVERSE_CUE_RE.sub(" ", rest)).strip()
        forced_anchor_coords = (c["lat"], c["lng"])
        folded = rest  # continue the pipeline on whatever text remains (may be "")

    # 1b. "toa do cua <POI>" — return the coordinates of a named POI. Only when no
    #     raw coordinate was given (that path is handled above).
    if parsed["coords"] is None:
        mlk = COORD_LOOKUP_RE.match(folded)
        if mlk and mlk.group(1).strip():
            folded = mlk.group(1).strip()
            entities["action"] = "coordinate_lookup"

    # 2. Sentinel detect + strip PRE-expansion.
    work, nav_hit = _strip_phrases(folded, ctx["nav_terms"])
    work, near_hit = _strip_phrases(work, ctx["nearby_terms"])
    parsed["nav"] = nav_hit
    parsed["nearby"] = near_hit

    # 3. Time extraction (pre-expansion).
    work, t = _extract_time(work)
    if t:
        parsed["time"] = t

    # 4. Expand + city detect.
    norm = expand_abbrev(work, terms, max_ngram)
    # Time again post-expansion (open late -> mo cua muon, 24h -> 24/7).
    norm, t2 = _extract_time(norm)
    if t2 and parsed["time"] is None:
        parsed["time"] = t2
    city_entry, norm_wo_city = gazetteer.detect_place(norm, gaz)
    parsed["city_entry"] = city_entry
    if city_entry:
        entities["city"] = city_entry["name"]
    parsed["normalized_query"] = expand_abbrev(fold(query), terms, max_ngram)

    body = norm_wo_city.strip()

    # 5. Navigation destination/origin (leading nav prep or "tu <origin>").
    if not nav_hit:
        for prep in ("di", "den", "toi"):
            if body == prep or body.startswith(prep + " "):
                # a bare leading "toi/den/di X" heads a destination
                if prep != "di" or " tu " in f" {body} ":
                    nav_hit = True
                    parsed["nav"] = True
                break
    if nav_hit:
        dest = body
        if " tu " in f" {dest} ":
            left, _, origin = dest.partition(" tu ")
            parsed["origin_text"] = origin.strip() or None
            if parsed["origin_text"]:
                entities["origin"] = parsed["origin_text"]
            dest = left.strip()
        # strip a leading nav preposition
        for prep in NAV_PREPS:
            if dest == prep or dest.startswith(prep + " "):
                dest = dest[len(prep):].strip()
                break
        parsed["destination_text"] = dest or None
        body = dest

    # 6. Proximity split (skip when navigation already owns the phrase).
    target = body
    if not nav_hit:
        split = _split_proximity(body)
        if split:
            left, right = split
            mce = COORD_RE.match(right) or COORD_EMBED_RE.search(right)
            if mce and _coords_in_range(float(mce.group(1)), float(mce.group(2))):
                parsed["anchor_coords"] = (float(mce.group(1)), float(mce.group(2)))
                parsed["nearby"] = True
                target = left
            elif right in HERE_WORDS or right.split()[:1] and right.split()[0] in HERE_WORDS:
                parsed["nearby"] = True
                target = left
            else:
                parsed["anchor_text"] = right
                parsed["nearby"] = True
                target = left

    parsed["target_text"] = target

    # 7. Category FIRST, then brand — a category word can be embedded in a brand
    #    name ("nha thuoc" = pharmacy AND the head of "Nha thuoc Long Chau"), so
    #    stripping the category exposes the distinctive brand tail.
    cat_key, remainder = None, target
    if detect_category and cat_idx is not None and target:
        cat_key, remainder = detect_category(target, cat_idx)
    brands, after_brand = _detect_brands(remainder, ctx)
    if not brands and cat_key:
        # brand whose name embeds the category word — scan the full target.
        brands, _ = _detect_brands(target, ctx)
    parsed["brands"] = brands
    if brands:
        entities.setdefault("brand", brands[0])
    parsed["category"] = cat_key
    parsed["remainder"] = (after_brand if brands else remainder).strip()
    # name_query keeps brand + street tokens for POI name matching.
    parsed["name_query"] = target.strip() or norm

    # 8. Address shape (only meaningful without a category on the target).
    addr = _detect_address(target, ctx)
    if addr:
        parsed["address"] = addr
        entities["house_number"] = addr["house_number"]
        entities["street"] = addr["street"]

    # A coordinate given ALONGSIDE a category/nearby/anchor request is the anchor
    # of a nearby search; a bare coordinate (or coordinate + "what is here" cue)
    # stays a coordinate/reverse-geocode lookup handled below.
    if forced_anchor_coords is not None and (
        parsed["category"] or parsed["nearby"] or parsed["anchor_text"] or parsed["brands"]
    ):
        parsed["anchor_coords"] = forced_anchor_coords
        parsed["nearby"] = True

    # --- Intent priority ---
    if parsed["anchor_coords"] is not None:
        parsed["intent"] = "nearby"
    elif parsed["coords"] is not None:
        parsed["intent"] = "reverse_geocode" if reverse_cue else "coordinate"
    elif nav_hit and parsed["destination_text"]:
        parsed["intent"] = "navigation"
    elif parsed["anchor_text"] is not None:
        parsed["intent"] = "nearby"
    elif parsed["nearby"]:
        parsed["intent"] = "nearby"
    elif addr and cat_key is None:
        parsed["intent"] = "address"
    elif cat_key and brands:
        parsed["intent"] = "brand_category"
    elif cat_key and city_entry and any(
        w in target for w in ("check", "song ao", "chup hinh", "chup anh", "so ao")
    ):
        # discovery = "find me a nice place to <check-in/photo> in <city>"
        parsed["intent"] = "discovery"
    elif cat_key:
        parsed["intent"] = "category"
    elif brands and not parsed["remainder"]:
        # bare brand — could be POI, store, or hotel: ambiguous
        parsed["intent"] = "ambiguous"
        parsed["ambiguous_hint"] = True
    else:
        parsed["intent"] = "poi"

    # Populate README-style entity hints.
    if cat_key:
        entities.setdefault("category", cat_key)
    if parsed["anchor_text"]:
        entities["reference"] = parsed["anchor_text"]
    if parsed["anchor_coords"]:
        entities["latitude"], entities["longitude"] = parsed["anchor_coords"]
    if parsed["nearby"] and not parsed["anchor_text"] and parsed["anchor_coords"] is None:
        entities.setdefault("location", "current_location")
    if parsed["time"]:
        entities["time"] = parsed["time"]
    if nav_hit:
        entities["action"] = "directions"
    return parsed


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Inspect the query-intent router")
    ap.add_argument("query")
    args = ap.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from search import _category_index, _detect_category, _load

    categories, _, _, _ = _load()
    cat_idx = _category_index(categories)
    p = parse(args.query, context(), _detect_category, cat_idx)
    p = {k: v for k, v in p.items() if k not in ("city_entry",)}
    p["competition_intent"] = competition_intent(p)
    print(json.dumps(p, ensure_ascii=True, indent=1))


if __name__ == "__main__":
    main()
