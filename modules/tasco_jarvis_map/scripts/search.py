"""Search CLI for the Tasco Jarvis Map dataset (Vietnam POIs + addresses).

Every subcommand prints ONE JSON object to stdout (ASCII-safe) and exits 0;
soft failures return {"error": "..."} so agent/dashboard callers never crash.

  search.py search "cafe q1" [--limit 8] [--city <fold>] [--category <key>]
  search.py near --lat 10.77 --lng 106.70 [--radius-km 2] [--category] [--limit 8]
  search.py geocode "283 nguyen hue q7"
  search.py pois [--city <fold>] [--category <key>]     # dashboard boot dump
  search.py categories

Run with PYTHONUTF8=1 on Windows.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gazetteer  # noqa: E402 — data-derived place index (no hardcoded places)
from _data import (  # noqa: E402
    emit,
    fold,
    haversine_km,
    load_abbreviations,
    load_json,
    normalize_query,
)

# Extra folded synonyms per canonical category (beyond folded label/label_vi).
CATEGORY_SYNONYMS = {
    "cafe": ["cafe", "cafes", "ca phe", "quan ca phe", "coffee", "coffee shop", "quan cafe", "tra sua", "cafe hoc bai"],
    "restaurant": ["nha hang", "restaurant", "restaurants", "quan an", "an uong", "do an", "food", "an dem", "quan an mo khuya"],
    "hotel": ["khach san", "hotel", "hotels"],
    "supermarket": ["sieu thi", "supermarket"],
    "convenience": ["cua hang tien loi", "tien loi", "convenience"],
    "mall": ["trung tam thuong mai", "tttm", "mall", "shopping"],
    "bank": ["ngan hang", "bank", "atm", "cay atm", "rut tien"],
    "cinema": ["rap chieu phim", "rap phim", "cinema", "xem phim", "rap"],
    "hospital": ["benh vien", "hospital", "bv"],
    "pharmacy": ["nha thuoc", "hieu thuoc", "pharmacy", "thuoc", "tiem thuoc"],
    "gas": ["cay xang", "tram xang", "gas", "xang", "do xang"],
    "ev_charging": ["tram sac", "tram sac dien", "sac dien", "sac xe dien", "ev"],
    "electronics": ["dien may", "electronics", "dien thoai", "may tinh"],
    "airport": ["san bay", "airport"],
    "bus_station": ["ben xe", "bus station"],
    "market": ["cho", "market"],
    "attraction": ["diem du lich", "du lich", "tham quan", "attraction", "attractions",
                   "checkin", "check in", "dia diem checkin", "diem checkin", "song ao"],
}


# Query-hygiene constants (language-level, like fold()'s đ->d — NOT place data).
LOCATION_STOPWORDS = frozenset({"o", "tai", "in", "at"})


def _strip_noise(text: str) -> str:
    """Drop location stopwords + tokens with no alphanumeric chars. Applied
    only to the post-place string feeding category/location scoring — never
    to the norm used for name scoring."""
    return " ".join(
        t for t in text.split()
        if t not in LOCATION_STOPWORDS and any(ch.isalnum() for ch in t)
    )


_GAZ = None


def _gazetteer() -> dict:
    """Place gazetteer derived from the dataset (built once per process)."""
    global _GAZ
    if _GAZ is None:
        _GAZ = gazetteer.build_from_data()
    return _GAZ


def _load():
    pois = load_json("pois.json")
    terms, max_ngram = load_abbreviations()
    return pois["categories"], pois["pois"], terms, max_ngram


def _category_index(categories: dict) -> dict[str, str]:
    """folded phrase -> category key, longest phrases first (for prefix scan)."""
    idx: dict[str, str] = {}
    for key, meta in categories.items():
        for phrase in [meta["label"], meta["label_vi"], *CATEGORY_SYNONYMS.get(key, [])]:
            idx[fold(phrase)] = key
    return idx


def _detect_category(norm: str, cat_idx: dict[str, str]) -> tuple[str | None, str]:
    """Find the longest category phrase inside the normalized query.

    Returns (category_key | None, remainder_query).
    """
    best_phrase, best_key = "", None
    padded = f" {norm} "
    for phrase, key in cat_idx.items():
        if f" {phrase} " in padded and len(phrase) > len(best_phrase):
            best_phrase, best_key = phrase, key
    if best_key is None:
        return None, norm
    remainder = padded.replace(f" {best_phrase} ", " ", 1).strip()
    return best_key, remainder


def _score_text(norm: str, keys: list[str]) -> float:
    """Score a normalized query against a POI's folded keys (name/en/aliases)."""
    if not norm:
        return 0.0
    best = 0.0
    q_tokens = set(norm.split())
    for i, k in enumerate(keys):
        if not k:
            continue
        alias_penalty = 0 if i == 0 else 5  # exact name 100, exact alias 95
        if norm == k:
            s = 100 - alias_penalty
        elif k.startswith(norm):
            s = 80 - alias_penalty
        elif norm in k:
            s = 60 - alias_penalty
        else:
            k_tokens = set(k.split())
            if q_tokens and q_tokens <= k_tokens:
                s = 50
            else:
                overlap = len(q_tokens & k_tokens) / max(len(q_tokens), 1)
                s = overlap * 40
        best = max(best, s)
    return best


def _poi_keys(p: dict) -> list[str]:
    return [p["q"]["name"], p["q"]["name_en"], *p["q"]["aliases"]]


def _coverage_score(norm: str, p: dict) -> float:
    """Brand+location queries ('vincom quan 1'): every query token must land in
    the name keys OR the address, and at least one must hit the name."""
    tokens = norm.split()
    if not tokens:
        return 0.0
    name_blob = " ".join(_poi_keys(p))
    addr = p["q"]["addr"]
    name_hits = sum(1 for t in tokens if t in name_blob)
    covered = sum(1 for t in tokens if t in name_blob or t in addr)
    if name_hits == 0 or covered < len(tokens):
        return 0.0
    return 45 + 25 * (name_hits / len(tokens))


def _location_score(remainder: str, p: dict) -> float:
    """How well leftover tokens (district/city/street words) match the address."""
    if not remainder:
        return 1.0  # no location constraint
    r_tokens = set(remainder.split())
    addr_tokens = set(p["q"]["addr"].split())
    hit = len(r_tokens & addr_tokens) / len(r_tokens)
    return hit


def _public(p: dict, score: float | None = None, distance_km: float | None = None) -> dict:
    out = {
        "poi_id": p["poi_id"], "name": p["name"], "name_en": p["name_en"],
        "category": p["category"], "lat": p["lat"], "lng": p["lng"],
        "address": p["address"], "district": p["district"], "city": p["city"],
        "rating": p["rating"], "opening_hours": p["opening_hours"],
    }
    if score is not None:
        out["score"] = round(score, 1)
    if distance_km is not None:
        out["distance_km"] = round(distance_km, 2)
    return out


def _dispatch(json_impl, db_name: str, args) -> dict:
    """Route to the Postgres engine (search_db) when ATRIA_MAP_BACKEND=db,
    silently falling back to the JSON engine on ANY db-side failure (stderr
    warning only — stdout shape never changes)."""
    import _db

    if _db.backend() == "db":
        try:
            import search_db

            return getattr(search_db, db_name)(args)
        except Exception as exc:
            print(f"WARN map-db unavailable, json fallback: {exc}", file=sys.stderr)
    return json_impl(args)


def cmd_search(args) -> dict:
    return _dispatch(_cmd_search_json, "cmd_search_db", args)


def cmd_near(args) -> dict:
    return _dispatch(_cmd_near_json, "cmd_near_db", args)


def cmd_geocode(args) -> dict:
    return _dispatch(_cmd_geocode_json, "cmd_geocode_db", args)


def cmd_pois(args) -> dict:
    return _dispatch(_cmd_pois_json, "cmd_pois_db", args)


def cmd_categories(args) -> dict:
    return _dispatch(_cmd_categories_json, "cmd_categories_db", args)


def _dispatch_db_only(db_name: str, args) -> dict:
    """GeoRAG-only tools have no JSON counterpart: soft-fail JSON on any error
    (same convention as the top-level handler — callers never crash)."""
    import _db

    if _db.backend() != "db":
        return {"error": "requires db backend (set ATRIA_MAP_BACKEND=db)"}
    try:
        import search_db

        return getattr(search_db, db_name)(args)
    except Exception as exc:
        return {"error": f"map-db unavailable: {type(exc).__name__}: {exc}"}


def cmd_reverse_geocode(args) -> dict:
    return _dispatch_db_only("cmd_reverse_geocode_db", args)


def cmd_find_duplicates(args) -> dict:
    return _dispatch_db_only("cmd_find_duplicates_db", args)


def cmd_explain_match(args) -> dict:
    return _dispatch_db_only("cmd_explain_match_db", args)


def _cmd_search_json(args) -> dict:
    categories, pois, terms, max_ngram = _load()
    raw = fold(args.query)
    norm = normalize_query(args.query, terms, max_ngram)
    gaz = _gazetteer()
    # Place pre-pass: detect a city mention (data-derived variants), strip it
    # plus noise tokens from the category/location string. Name scoring below
    # still uses the full norm/raw.
    place, rest = gazetteer.detect_place(norm, gaz)
    rest = _strip_noise(rest)
    cat_idx = _category_index(categories)
    cat_key, remainder = _detect_category(rest, cat_idx)
    if args.category:
        cat_key = args.category
    eff_city = (
        gazetteer.resolve_place(args.city, gaz) if args.city
        else (place["canonical"] if place else None)
    )

    scored: list[tuple[float, dict]] = []
    for p in pois:
        if eff_city and eff_city not in fold(p["city"]):
            continue  # HARD city filter — precision over recall
        keys = _poi_keys(p)
        # score both expanded and raw-folded query (aliases may match either)
        name_s = max(_score_text(norm, keys), _score_text(raw, keys) if raw != norm else 0,
                     _coverage_score(norm, p))
        if cat_key and p["category"] == cat_key:
            # category query: score the remainder as a location/name constraint
            loc = _location_score(remainder, p)
            rem_name = _score_text(remainder, _poi_keys(p)) if remainder else 0
            cat_s = 55 + 35 * max(loc, rem_name / 100)
            s = max(name_s, cat_s)
        elif cat_key and remainder == "":
            s = name_s * 0.3  # pure category query — other categories fade
        else:
            s = name_s
        if s > 20:
            scored.append((s + (p["rating"] or 0) / 100, p))

    scored.sort(key=lambda t: -t[0])
    top = scored[: args.limit]
    return {
        "query": args.query,
        "normalized_query": norm,
        "category": cat_key,
        "city": eff_city,
        "results": [_public(p, score=s) for s, p in top],
        "count": len(top),
    }


def _cmd_near_json(args) -> dict:
    _, pois, _, _ = _load()
    rows = []
    for p in pois:
        if args.category and p["category"] != args.category:
            continue
        d = haversine_km(args.lat, args.lng, p["lat"], p["lng"])
        if d <= args.radius_km:
            rows.append((d, p))
    rows.sort(key=lambda t: t[0])
    top = rows[: args.limit]
    return {
        "origin": {"lat": args.lat, "lng": args.lng},
        "radius_km": args.radius_km,
        "category": args.category,
        "results": [_public(p, distance_km=d) for d, p in top],
        "count": len(top),
    }


def _cmd_geocode_json(args) -> dict:
    categories, pois, terms, max_ngram = _load()
    addresses = load_json("addresses.json")["addresses"]
    norm = normalize_query(args.query, terms, max_ngram)
    cands: list[tuple[float, str, dict]] = []
    for a in addresses:
        keys = [a["q"]["full"], *a["q"]["aliases"]]
        s = _score_text(norm, keys)
        if s > 20:
            cands.append((s, "address", a))
    for p in pois:
        s = _score_text(norm, _poi_keys(p))
        if s > 20:
            cands.append((s, "poi", p))
    cands.sort(key=lambda t: -t[0])
    if not cands:
        return {"query": args.query, "normalized_query": norm, "match": None, "alternates": []}

    def pub(kind: str, row: dict) -> dict:
        if kind == "poi":
            return {"kind": "poi", "id": row["poi_id"], "name": row["name"],
                    "lat": row["lat"], "lng": row["lng"], "full_address": row["address"]}
        return {"kind": "address", "id": row["address_id"], "name": row["full_address"],
                "lat": row["lat"], "lng": row["lng"], "full_address": row["full_address"]}

    best = cands[0]
    return {
        "query": args.query,
        "normalized_query": norm,
        "match": pub(best[1], best[2]),
        "score": round(best[0], 1),
        "alternates": [pub(k, r) for _, k, r in cands[1:4]],
    }


def _cmd_pois_json(args) -> dict:
    categories, pois, terms, max_ngram = _load()
    rows = pois
    if args.city:
        city = gazetteer.resolve_place(args.city, _gazetteer())
        rows = [p for p in rows if city in fold(p["city"])]
    if args.category:
        rows = [p for p in rows if p["category"] == args.category]
    # abbreviations ride along so the dashboard can mirror query expansion
    return {"categories": categories, "pois": rows, "count": len(rows),
            "abbreviations": {"terms": terms, "max_ngram": max_ngram}}


def _cmd_categories_json(args) -> dict:
    categories, pois, _, _ = _load()
    counts: dict[str, int] = {}
    for p in pois:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    return {"categories": categories, "counts": counts}


def main() -> None:
    ap = argparse.ArgumentParser(description="Tasco Jarvis Map search CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search"); s.add_argument("query")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--city"); s.add_argument("--category")

    n = sub.add_parser("near")
    n.add_argument("--lat", type=float, required=True)
    n.add_argument("--lng", type=float, required=True)
    n.add_argument("--radius-km", type=float, default=3.0)
    n.add_argument("--category"); n.add_argument("--limit", type=int, default=8)

    g = sub.add_parser("geocode"); g.add_argument("query")

    p = sub.add_parser("pois"); p.add_argument("--city"); p.add_argument("--category")

    sub.add_parser("categories")

    rg = sub.add_parser("reverse_geocode")
    rg.add_argument("--lat", type=float, required=True)
    rg.add_argument("--lng", type=float, required=True)
    rg.add_argument("--limit", type=int, default=3)

    d = sub.add_parser("find_duplicates")
    d.add_argument("--threshold", type=float, default=0.75)
    d.add_argument("--radius-m", type=float, default=150.0)

    e = sub.add_parser("explain_match"); e.add_argument("query")
    e.add_argument("--poi-id", required=True)

    args = ap.parse_args()
    try:
        result = {"search": cmd_search, "near": cmd_near, "geocode": cmd_geocode,
                  "pois": cmd_pois, "categories": cmd_categories,
                  "reverse_geocode": cmd_reverse_geocode,
                  "find_duplicates": cmd_find_duplicates,
                  "explain_match": cmd_explain_match}[args.cmd](args)
    except Exception as exc:  # soft-fail JSON for agent/dashboard callers
        result = {"error": f"{type(exc).__name__}: {exc}"}
    emit(result)


if __name__ == "__main__":
    main()
