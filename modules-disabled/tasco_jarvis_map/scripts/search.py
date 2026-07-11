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
import query_intent  # noqa: E402 — language-level intent router (no hardcoded places)
from _data import (  # noqa: E402
    emit,
    fold,
    haversine_km,
    is_open_at,
    load_abbreviations,
    load_json,
    normalize_query,
    open_after,
    parse_opening_hours,
)

# Anchor resolution: proximity queries ("X gan <landmark>") need the landmark
# geocoded to a coordinate. A candidate below this legacy score is not a
# confident anchor -> the tentative proximity split is reverted (plain search).
ANCHOR_MIN = 50.0
RADIUS_COORD_KM = 1.0
RADIUS_ADDRESS_KM = 2.0
RADIUS_LANDMARK_KM = 3.0
# Category-aware default nearby radius (km). Sparse-service categories get a wider
# reach; dense food/retail stays tight. Falls back to the anchor-kind base when a
# category is absent or unlisted. A user-supplied radius always overrides.
RADIUS_BY_CATEGORY_KM = {
    "hospital": 5.0, "gas": 5.0, "ev_charging": 5.0,
    "supermarket": 3.0, "mall": 3.0, "cinema": 3.0, "hotel": 3.0, "electronics": 3.0,
    "pharmacy": 2.0, "bank": 2.0,
    "cafe": 1.5, "restaurant": 1.5, "convenience": 1.5,
}


def _category_radius(category: str | None, base: float) -> float:
    """Category-aware nearby radius, else the anchor-kind `base`."""
    return RADIUS_BY_CATEGORY_KM.get(category or "", base)

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


def _parse_with_flags(args, categories: dict, terms: dict, max_ngram: int) -> dict:
    """Router parse + CLI time-flag overrides. Shared by the wrapper and both
    plain engines so intent/brands/time/city are derived identically."""
    ctx = query_intent.context()
    cat_idx = _category_index(categories)
    parsed = query_intent.parse(args.query, ctx, _detect_category, cat_idx)
    open_after_flag = getattr(args, "open_after", None)
    if open_after_flag:
        try:
            hh, mm = open_after_flag.split(":")
            parsed["time"] = {"after_min": int(hh) * 60 + int(mm)}
        except (ValueError, AttributeError):
            pass
    elif getattr(args, "open_now", False):
        parsed["time"] = {"open_now": True}
    return parsed


def _bare_city_update(parsed: dict) -> bool:
    """True when a turn supplies ONLY a city (a follow-up like 'toi o SG') and
    nothing else — even if the router misfired the intent to navigation (a bare
    'toi o ...' can do that). Such a turn should re-scope the prior request."""
    return bool(
        parsed.get("city_entry")
        and not parsed.get("category")
        and not parsed.get("brands")
        and parsed.get("coords") is None
        and parsed.get("anchor_text") is None
        and parsed.get("anchor_coords") is None
    )


def _city_entry_for(canonical: str):
    """Reconstruct a gazetteer city entry from a cached canonical name."""
    try:
        return query_intent.context()["gaz"]["city_idx"].get(canonical)
    except Exception:  # noqa: BLE001 - context/gaz unavailable -> skip the lever
        return None


def _merge_prior(args, parsed: dict) -> None:
    """Fold prior-turn slots into the current parse so a conversation continues
    in-context. ``args.prior`` is a dict of the last turn's resolved slots and is
    set ONLY by the interactive jarvis_chat path — the benchmark/eval never set
    it, so this is a strict no-op for them (gates untouched).

    R1 bare-city-update: a city-only follow-up inherits the prior category/intent
        and re-runs the prior search scoped to the NEW city ('benh vien' -> 'SG'
        => hospitals in HCMC). Also undoes the spurious navigation misfire.
    R2 city carry-forward: a category/brand turn with no city inherits the prior
        city ('nha thuoc' after a city was established).

    Writes BOTH steering levers: args.city/args.category (the plain engines read
    only these) and parsed city_entry/category/intent (the geometric branches
    read only these)."""
    prior = getattr(args, "prior", None)
    if not prior or not isinstance(prior, dict):
        return
    prior_city = prior.get("city_canonical")
    prior_cat = prior.get("category")

    # R1: the current turn is only a city; inherit what the user was asking for
    # and scope it to the freshly named city.
    if _bare_city_update(parsed) and prior_cat:
        parsed["category"] = prior_cat
        args.category = prior_cat
        parsed["intent"] = "category"
        parsed["nav"] = False               # cancel the 'toi o ...' nav misfire
        parsed["destination_text"] = None
        parsed["origin_text"] = None
        parsed["_inherited"] = True
        args.city = parsed["city_entry"]["canonical"]
        return

    # R2: a content turn with no city of its own inherits the prior city.
    if prior_city and parsed.get("city_entry") is None and not getattr(args, "city", None):
        args.city = prior_city
        entry = _city_entry_for(prior_city)
        if entry is not None:
            parsed["city_entry"] = entry
        parsed["_inherited"] = True


def _confidence(intent: str, results: list, anchor: dict | None) -> float:
    """A 0..1 confidence for the README output contract."""
    if not results:
        return 0.3
    if intent == "Coordinate Search":
        return 0.9
    if intent == "Ambiguous":
        return 0.4
    if anchor:
        return 0.85 if anchor.get("resolution") in ("exact", "category_best") else 0.65
    top = results[0].get("score")
    if top is not None:
        return round(min(0.99, max(0.3, top / 100.0)), 2)
    return 0.7


def cmd_search(args) -> dict:
    """Intent router. Geometric intents (coordinate / navigation / nearby with a
    resolved anchor) are answered by shared helpers over the JSON data — identical
    for both backends. Only PLAIN scoring dispatches to the active engine."""
    categories, pois, terms, max_ngram = _load()
    parsed = _parse_with_flags(args, categories, terms, max_ngram)
    _merge_prior(args, parsed)  # multi-turn context (no-op unless args.prior set)
    intent = parsed["intent"]

    if intent in ("coordinate", "reverse_geocode") and parsed["coords"] is not None:
        reverse = intent == "reverse_geocode"
        anchor = {"kind": "coordinate",
                  "label": f"{parsed['coords'][0]:.4f},{parsed['coords'][1]:.4f}",
                  "lat": parsed["coords"][0], "lng": parsed["coords"][1],
                  "resolution": "reverse" if reverse else "exact",
                  "radius_km": RADIUS_COORD_KM}
        resp = _anchored_response(args, parsed, pois, parsed["coords"], anchor)
        if reverse:
            # "what is here?" — same nearest-POI retrieval, but flagged so the
            # reply describes the location instead of listing nearby options.
            resp["reverse_geocode"] = True
        return resp
    if intent == "navigation" and parsed["destination_text"]:
        return _navigation_response(args, parsed, categories, pois, terms, max_ngram)
    if intent == "nearby" and (parsed["anchor_text"] or parsed["anchor_coords"] is not None):
        addresses = load_json("addresses.json")["addresses"]
        anchor_city = parsed["city_entry"]["canonical"] if parsed["city_entry"] else None
        anchor = _resolve_anchor(parsed, pois, addresses, terms, max_ngram, city=anchor_city)
        if anchor is not None:
            return _anchored_response(args, parsed, pois,
                                      (anchor["lat"], anchor["lng"]), anchor)
        # tentative-split revert: anchor unresolved -> plain, city-filtered search

    resp = _dispatch(_cmd_search_json, "cmd_search_db", args)
    if parsed.get("_inherited"):
        # The plain engines re-parse the raw text internally, so a follow-up like
        # "toi o SG" re-derives its nav misfire there and mislabels the response.
        # Restamp the intent from the authoritative merged parse.
        resp["intent"] = query_intent.competition_intent(parsed)
    return resp


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


REVERSE_AMBIGUOUS_M = 25.0
REVERSE_NOT_FOUND_M = 2000.0


def _cmd_reverse_geocode_json(args) -> dict:
    """JSON counterpart of cmd_reverse_geocode_db: nearest place/address for a
    coordinate by haversine over pois + addresses (same output shape)."""
    _, pois, _, _ = _load()
    addresses = load_json("addresses.json")["addresses"]
    rows = []
    for p in pois:
        d_m = haversine_km(args.lat, args.lng, p["lat"], p["lng"]) * 1000.0
        rows.append({"kind": "poi", "id": p["poi_id"], "name": p["name"],
                     "full_address": p["address"], "lat": p["lat"], "lng": p["lng"],
                     "distance_m": round(d_m, 1)})
    for a in addresses:
        d_m = haversine_km(args.lat, args.lng, a["lat"], a["lng"]) * 1000.0
        rows.append({"kind": "address", "id": a["address_id"], "name": a["full_address"],
                     "full_address": a["full_address"], "lat": a["lat"], "lng": a["lng"],
                     "distance_m": round(d_m, 1)})
    rows.sort(key=lambda r: r["distance_m"])
    rows = rows[: args.limit]
    if not rows or rows[0]["distance_m"] > REVERSE_NOT_FOUND_M:
        return {"origin": {"lat": args.lat, "lng": args.lng},
                "match": None, "alternates": rows, "status": "not_found"}
    match, alternates = rows[0], rows[1:]
    status = "success"
    if alternates and alternates[0]["distance_m"] - match["distance_m"] < REVERSE_AMBIGUOUS_M:
        status = "ambiguous"
    return {"origin": {"lat": args.lat, "lng": args.lng},
            "match": match, "alternates": alternates, "status": status}


def cmd_reverse_geocode(args) -> dict:
    return _dispatch(_cmd_reverse_geocode_json, "cmd_reverse_geocode_db", args)


def cmd_find_duplicates(args) -> dict:
    return _dispatch_db_only("cmd_find_duplicates_db", args)


def cmd_explain_match(args) -> dict:
    return _dispatch_db_only("cmd_explain_match_db", args)


def _brand_hit(brands: list[str], p: dict) -> bool:
    """Does POI `p` belong to any of the parsed (folded canonical) brands?"""
    if not brands:
        return False
    pb = fold(p.get("brand") or "")
    blob = " ".join(_poi_keys(p))
    for b in brands:
        if not b:
            continue
        if pb and (pb == b or pb.startswith(b + " ") or b == pb.split()[0] or b in pb):
            return True
        if f" {b} " in f" {blob} ":
            return True
    return False


def _time_ok(p: dict, time_c: dict | None, now_min: int) -> bool:
    """Apply a router/CLI time constraint to a POI's opening_hours."""
    if not time_c:
        return True
    spec = p.get("opening_hours")
    if time_c.get("full_day"):
        return parse_opening_hours(spec) == (0, 1440)
    if time_c.get("open_now"):
        return is_open_at(spec, now_min)
    if "after_min" in time_c:
        return open_after(spec, time_c["after_min"])
    return True


def _now_minutes(args) -> int:
    """Deterministic 'current minute of day' for open_now (eval passes --now)."""
    val = getattr(args, "now", None)
    if val:
        try:
            hh, mm = val.split(":")
            return (int(hh) * 60 + int(mm)) % 1440
        except (ValueError, AttributeError):
            pass
    return 12 * 60  # noon default — deterministic without a real clock


def _resolve_anchor(parsed: dict, pois: list[dict], addresses: list[dict],
                    terms: dict, max_ngram: int, city: str | None = None) -> dict | None:
    """Geocode a proximity anchor to a coordinate, reusing legacy geocode
    scoring over POIs + addresses. When a city was detected, the anchor must lie
    in it (so 'bien' in Da Nang cannot resolve to Ha Noi's 'Dien Bien Phu').
    Returns an anchor dict or None (which reverts the tentative proximity split
    to a plain, city-filtered full-query search)."""
    if parsed["anchor_coords"] is not None:
        lat, lng = parsed["anchor_coords"]
        return {"kind": "coordinate", "label": f"{lat:.4f},{lng:.4f}",
                "lat": lat, "lng": lng, "resolution": "exact",
                "radius_km": RADIUS_COORD_KM}
    text = parsed["anchor_text"]
    if not text:
        return None
    norm = normalize_query(text, terms, max_ngram)
    best_s, best_kind, best_row = 0.0, None, None
    for a in addresses:
        if city and city not in fold(a.get("city") or ""):
            continue
        s = _score_text(norm, [a["q"]["full"], *a["q"]["aliases"]])
        if s > best_s:
            best_s, best_kind, best_row = s, "address", a
    for p in pois:
        if city and city not in fold(p.get("city") or ""):
            continue
        s = _score_text(norm, _poi_keys(p))
        if s > best_s:
            best_s, best_kind, best_row = s, "poi", p
    if best_row is None or best_s < ANCHOR_MIN:
        return None
    resolution = "exact" if best_s >= 80 else "nearest_candidate"
    if best_kind == "address":
        label = best_row["full_address"]
        radius = RADIUS_ADDRESS_KM
    else:
        label = best_row["name"]
        radius = RADIUS_LANDMARK_KM
    return {"kind": best_kind, "label": label, "lat": best_row["lat"],
            "lng": best_row["lng"], "resolution": resolution, "radius_km": radius}


def _anchored_response(args, parsed: dict, pois: list[dict], origin: tuple[float, float],
                       anchor: dict) -> dict:
    """Distance-ranked results around a resolved anchor / coordinate, honoring
    the parsed category, brands and time constraint. Widens the radius once if
    the first pass is empty (disclosed in anchor.radius_km)."""
    lat, lng = origin
    category = args.category or parsed["category"]
    brands = parsed["brands"]
    now_min = _now_minutes(args)
    city = parsed["city_entry"]["canonical"] if parsed["city_entry"] else None
    # Effective radius: an explicit user radius wins; else a category-aware default;
    # else the anchor-kind base. Disclosed back via anchor.radius_km.
    user_radius = getattr(args, "radius_km", None)
    anchor = {**anchor, "radius_km": user_radius or _category_radius(category, anchor["radius_km"])}

    def collect(radius: float) -> list[tuple[float, dict]]:
        out = []
        for p in pois:
            if category and p["category"] != category:
                continue
            if city and city not in fold(p.get("city") or ""):
                continue
            if not _time_ok(p, parsed["time"], now_min):
                continue
            d = haversine_km(lat, lng, p["lat"], p["lng"])
            if d <= radius:
                out.append((d, p))
        return out

    radius = anchor["radius_km"]
    rows = collect(radius)
    if not rows:
        radius *= 2
        rows = collect(radius)
        anchor = {**anchor, "radius_km": radius}
    if not rows:
        # Nearest-available fallback: the sparse dataset may have no in-radius POI
        # of this category near the anchor (e.g. no hospital near an airport).
        # Return the nearest matching ones ANYWAY, disclosed via resolution +
        # actual radius, instead of an empty (and unhelpful) result.
        allc = []
        for p in pois:
            if category and p["category"] != category:
                continue
            if city and city not in fold(p.get("city") or ""):
                continue
            if not _time_ok(p, parsed["time"], now_min):
                continue
            allc.append((haversine_km(lat, lng, p["lat"], p["lng"]), p))
        allc.sort(key=lambda t: t[0])
        if allc:
            # Keep the nearest, then only others within a band relative to it, so
            # we never pad the list across a large gap (e.g. 4 hospitals ~20 km
            # from the anchor + one 600 km away in another city). The band is
            # data-relative, not a hardcoded radius.
            near_d = allc[0][0]
            band = max(near_d * 3.0, near_d + 25.0)
            rows = [t for t in allc if t[0] <= band][: args.limit]
            anchor = {**anchor, "resolution": "nearest_available",
                      "radius_km": round(rows[-1][0], 1)}
    if brands:
        branded = [r for r in rows if _brand_hit(brands, r[1])]
        if branded:
            rows = branded
    rows.sort(key=lambda t: t[0])
    top = rows[: args.limit]
    intent_label = query_intent.competition_intent(parsed)
    results = [_public(p, distance_km=d) for d, p in top]
    resp_city = parsed["city_entry"]["canonical"] if parsed["city_entry"] else None
    return {
        "query": args.query,
        "normalized_query": parsed["normalized_query"],
        "category": category,
        "city": resp_city,
        "intent": intent_label,
        "anchor": anchor,
        "place_scope": None,
        "geo_contract": _geo_contract(resp_city, None, anchor, results),
        "entities": parsed["entities"],
        "confidence_score": _confidence(intent_label, results, anchor),
        "results": results,
        "count": len(top),
    }


def _navigation_response(args, parsed: dict, categories: dict, pois: list[dict],
                         terms: dict, max_ngram: int) -> dict:
    """Resolve the destination of a navigation query to a single POI (+ its
    category), returning it as the sole result so the dashboard can route to it.
    No routing engine — a straight-line focus target, disclosed as such."""
    dest_text = parsed["destination_text"] or ""
    dest = _resolve_anchor(
        {"anchor_coords": None, "anchor_text": dest_text}, pois,
        load_json("addresses.json")["addresses"], terms, max_ngram)
    results = []
    anchor = None
    if dest and dest["kind"] == "poi":
        target = next((p for p in pois if p["name"] == dest["label"]), None)
        if target:
            results = [_public(target, distance_km=None)]
        anchor = {"kind": "poi", "label": dest["label"], "lat": dest["lat"],
                  "lng": dest["lng"], "resolution": dest["resolution"], "radius_km": None}
    elif dest:  # address destination
        anchor = {"kind": dest["kind"], "label": dest["label"], "lat": dest["lat"],
                  "lng": dest["lng"], "resolution": dest["resolution"], "radius_km": None}
    if not results and parsed["category"]:
        # destination is a category ("chi duong den san bay"): pin the best of them
        cands = [p for p in pois if p["category"] == parsed["category"]]
        cands.sort(key=lambda p: -(p.get("rating") or 0))
        if cands:
            results = [_public(cands[0], distance_km=None)]
            anchor = {"kind": "poi", "label": cands[0]["name"], "lat": cands[0]["lat"],
                      "lng": cands[0]["lng"], "resolution": "category_best", "radius_km": None}
    return {
        "query": args.query,
        "normalized_query": parsed["normalized_query"],
        "category": parsed["category"],
        "city": (parsed["city_entry"]["canonical"] if parsed["city_entry"] else None),
        "intent": "Navigation",
        "anchor": anchor,
        "place_scope": None,
        "geo_contract": _geo_contract(
            parsed["city_entry"]["canonical"] if parsed["city_entry"] else None,
            None, anchor, results),
        "entities": parsed["entities"],
        "confidence_score": _confidence("Navigation", results, anchor),
        "results": results,
        "count": len(results),
    }


_SCOPE_SETS = None


def _scope_sets() -> tuple[set, set, dict]:
    """Data-derived (districts, streets-only, district->city) for sub-city place
    filtering. Districts come from POIs; streets from the query_intent street set
    minus the districts; the district->city map (from POIs + addresses) has no
    cross-city collisions in this data. Cached, nothing hardcoded."""
    global _SCOPE_SETS
    if _SCOPE_SETS is None:
        pois = load_json("pois.json")["pois"]
        addresses = load_json("addresses.json").get("addresses", [])
        districts = {fold(p["district"]) for p in pois if p.get("district")}
        streets = set(query_intent.context()["streets"]) - districts
        d2c: dict[str, set] = {}
        for row in (*pois, *addresses):
            dd, cc = fold(row.get("district") or ""), fold(row.get("city") or "")
            if dd and cc:
                d2c.setdefault(dd, set()).add(cc)
        district_city = {d: next(iter(cs)) for d, cs in d2c.items() if len(cs) == 1}
        _SCOPE_SETS = (districts, streets, district_city)
    return _SCOPE_SETS


def _detect_scope(norm: str, districts: set, streets: set) -> tuple[str | None, str | None]:
    """Longest-first scan for a district and/or street named in the query."""
    padded = f" {norm} "
    d = next((x for x in sorted(districts, key=len, reverse=True)
              if x and f" {x} " in padded), None)
    st = next((x for x in sorted(streets, key=len, reverse=True)
               if x and f" {x} " in padded), None)
    return d, st


def _apply_scope(scored: list, norm: str) -> tuple[list, dict | None]:
    """Keep only results within a named district (or street) when any exist;
    otherwise leave results unfiltered and return a scope note so the reply can
    disclose 'none in <place>'. Precision for 'VCB Quận 7', 'VCB Nguyễn Huệ'.
    `scored` is a list of (score, poi_dict); works for either engine."""
    districts, streets, district_city = _scope_sets()
    d_hit, st_hit = _detect_scope(norm, districts, streets)
    if not scored:
        return scored, None
    if d_hit:
        ins = [(s, p) for s, p in scored if d_hit in fold(p.get("district") or "")]
        if ins:
            return ins, None
        # No result in that district. NEVER leak other cities: narrow to the
        # district's own city when known, and disclose 'none in <district>'.
        city = district_city.get(d_hit)
        if city:
            scoped = [(s, p) for s, p in scored if city in fold(p.get("city") or "")]
            return (scoped or scored), {"district": d_hit, "matched": False}
        return scored, {"district": d_hit, "matched": False}
    if st_hit:
        ins = [(s, p) for s, p in scored
               if st_hit in fold((p.get("name") or "") + " " + (p.get("address") or ""))]
        return (ins, None) if ins else (scored, {"street": st_hit, "matched": False})
    return scored, None


def _geo_contract(city: str | None, scope_note: dict | None,
                  anchor: dict | None, results: list[dict]) -> dict:
    """Consolidated geo metadata for every search response. `multi_city_leak_detected`
    is a regression tripwire: it flags results spanning >1 city when a city or
    district/street scope WAS named (an anchor+radius spanning a border is legit and
    does not trip it)."""
    result_cities = {fold(r.get("city") or "") for r in results if r.get("city")}
    hard = []
    if city:
        hard.append("city")
    if scope_note and scope_note.get("district"):
        hard.append("district")
    if scope_note and scope_note.get("street"):
        hard.append("street")
    if anchor and anchor.get("radius_km"):
        hard.append("radius")
    named_scope = bool(city) or bool(scope_note)
    return {
        "scope_status": "resolved" if (named_scope or anchor) else "open",
        "city": city,
        "scope": scope_note,
        "anchor": ({"label": anchor.get("label"), "lat": anchor.get("lat"),
                    "lng": anchor.get("lng")} if anchor else None),
        "radius_km": anchor.get("radius_km") if anchor else None,
        "hard_filters_applied": hard,
        "multi_city_leak_detected": named_scope and len(result_cities) > 1,
        "needs_clarification": False,
    }


def _cmd_search_json(args) -> dict:
    """PLAIN scoring for the JSON engine (poi / category / brand / address /
    nearby-no-anchor / reverted-anchor). Geometric intents are handled upstream
    in cmd_search; here we apply the city filter, brand branch/filter, time
    filter and legacy text scoring."""
    categories, pois, terms, max_ngram = _load()
    raw = fold(args.query)
    norm = normalize_query(args.query, terms, max_ngram)
    gaz = _gazetteer()
    parsed = _parse_with_flags(args, categories, terms, max_ngram)
    cat_idx = _category_index(categories)
    now_min = _now_minutes(args)

    place, rest = gazetteer.detect_place(norm, gaz)
    rest = _strip_noise(rest)
    cat_key, remainder = _detect_category(rest, cat_idx)
    if args.category:
        cat_key = args.category
    eff_city = (
        gazetteer.resolve_place(args.city, gaz) if args.city
        else (place["canonical"] if place else None)
    )
    brand_remainder = parsed["remainder"]
    # Brand + category ("atm vcb", "nt long chau q1") = the brand is a hard
    # filter: the user named a specific chain, so a different chain of the same
    # category is wrong. Applied only when the brand actually has a POI in that
    # category (a spurious brand hit never empties the results).
    brand_filter = bool(parsed["brands"]) and bool(cat_key) and any(
        p["category"] == cat_key and _brand_hit(parsed["brands"], p) for p in pois
    )

    scored: list[tuple[float, dict]] = []
    for p in pois:
        if eff_city and eff_city not in fold(p["city"]):
            continue  # HARD city filter — precision over recall
        if not _time_ok(p, parsed["time"], now_min):
            continue  # opening-hours constraint from the router
        if brand_filter and not _brand_hit(parsed["brands"], p):
            continue  # named-brand precision
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
        elif cat_key:
            # off-category for a CATEGORY search: keep only a near-exact NAME match
            # (the query actually named this specific POI); everything else is
            # off-category noise and must not pad the list (precision > recall).
            s = name_s * 0.5 if name_s >= 80 else 0.0
        else:
            s = name_s
        if parsed["brands"] and _brand_hit(parsed["brands"], p):
            # brand branch: floor 58 lifts a brand match above street-token noise;
            # the remainder is scored against the POI NAME only (never the address
            # district tokens — 'dong khoi' must not match 'Dong Da'), so the
            # branch whose street matches wins. Ceiling 92 < exact-alias 95.
            rem_name = _score_text(brand_remainder, keys) / 100 if brand_remainder else 0.0
            s = max(s, 58 + 34 * rem_name)
        if s > 20:
            scored.append((s + (p["rating"] or 0) / 100, p))

    # Sub-city scope: keep only results in a named district/street when present.
    scored, scope_note = _apply_scope(scored, norm)
    scored.sort(key=lambda t: -t[0])
    top = scored[: args.limit]
    # The intent stays as parsed even when a landmark anchor failed to resolve:
    # the USER intent is still a nearby search; only the retrieval degraded (to a
    # plain, city-filtered search) — disclosed by anchor=null.
    intent_label = query_intent.competition_intent(parsed)
    results = [_public(p, score=s) for s, p in top]
    return {
        "query": args.query,
        "normalized_query": norm,
        "category": cat_key,
        "city": eff_city,
        "intent": intent_label,
        "anchor": None,
        "place_scope": scope_note,
        "geo_contract": _geo_contract(eff_city, scope_note, None, results),
        "entities": parsed["entities"],
        "confidence_score": _confidence(intent_label, results, None),
        "results": results,
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
    s.add_argument("--open-after", dest="open_after", help="keep POIs open at/after HH:MM")
    s.add_argument("--open-now", dest="open_now", action="store_true",
                   help="keep POIs open at --now (default noon)")
    s.add_argument("--now", help="deterministic current time HH:MM for --open-now")

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
