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
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gazetteer  # noqa: E402 — data-derived place index (no hardcoded places)
import need_taxonomy  # noqa: E402 — controlled need vocab (hard/soft, no places)
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
    # "cho" (chợ) dropped as a bare synonym: it folds identically to the very
    # common function word "cho" (=for, "quán cho gia đình"), which mis-fired the
    # market category on non-market queries. Markets are still found by name
    # ("Chợ Bến Thành") and the "market" token.
    "market": ["market"],
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


# Folded category phrases that collide with a common function word and so must
# not, on their own, trigger a category. "cho" is both fold("Chợ") (market) and
# the ubiquitous particle "cho" (=for, "quán cho gia đình") — letting it fire the
# market category mis-routed every "... cho ..." query with no stronger category.
# Markets are still found by name ("Chợ Bến Thành") and the English "market".
_CATEGORY_PHRASE_IGNORE = frozenset({"cho"})


def _category_index(categories: dict) -> dict[str, str]:
    """folded phrase -> category key, longest phrases first (for prefix scan)."""
    idx: dict[str, str] = {}
    for key, meta in categories.items():
        for phrase in [meta["label"], meta["label_vi"], *CATEGORY_SYNONYMS.get(key, [])]:
            folded = fold(phrase)
            if folded in _CATEGORY_PHRASE_IGNORE:
                continue
            idx[folded] = key
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


def _public(p: dict, score: float | None = None, distance_km: float | None = None,
            reasons: list[str] | None = None) -> dict:
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
    if reasons:
        out["reasons"] = reasons
    return out


def _popularity_bonus(p: dict) -> float:
    """A sub-1 ranking tiebreak from rating + popularity + review volume, so it
    only orders POIs already tied on the primary 0-100 score and never crosses a
    score band. Legacy POIs (no popularity/review) fall back to the rating-only
    term, preserving their prior order."""
    rating = (p.get("rating") or 0) / 100.0                       # 0 .. 0.05
    pop = (p.get("popularity_score") or 0) / 10000.0              # 0 .. 0.0098
    rev = math.log10((p.get("review_count") or 0) + 1) / 1000.0   # ~0 .. 0.0042
    return rating + pop + rev


def _attr_frac(qattr: set[str], p: dict) -> float:
    """Fraction of the query's amenity tokens the POI satisfies (via its xfold'd
    q.attrs). 0 when the query names no amenity or the POI has none."""
    if not qattr:
        return 0.0
    poi_attr = p["q"].get("attrs", "")
    if not poi_attr:
        return 0.0
    return len(qattr & set(poi_attr.split())) / len(qattr)


# Reason-token hygiene: connectors/particles that must not, on their own, link a
# query to a POI phrase. Language-level (like fold's đ->d) — no place data.
_REASON_STOP = frozenset(
    {"de", "va", "co", "cua", "cac", "mot", "the", "for", "with", "and", "in",
     "at", "o", "tai", "la", "khong", "rat", "nhieu", "gio"}
)
_CAT_PHRASES: frozenset[str] | None = None


def _category_phrases() -> frozenset[str]:
    """Folded category labels + synonyms, cached — a phrase equal to one of these
    is the category itself, never a distinguishing 'reason' (skip 'cà phê' etc.)."""
    global _CAT_PHRASES
    if _CAT_PHRASES is None:
        cats = load_json("pois.json")["categories"]
        phrases = set()
        for key, meta in cats.items():
            for ph in [meta["label"], meta["label_vi"], *CATEGORY_SYNONYMS.get(key, [])]:
                phrases.add(fold(ph))
        _CAT_PHRASES = frozenset(phrases)
    return _CAT_PHRASES


def _match_reasons(p: dict, qattr: set[str], query: str, terms: dict, max_ngram: int) -> list[str]:
    """The POI's own amenity/tag phrases that satisfy the query — the human-readable
    'why this matches' (e.g. ['wifi', 'yên tĩnh', 'phù hợp làm việc']). A phrase is
    surfaced when its folded tokens overlap the query's detected amenity tokens
    (qattr) OR the query's own content tokens, so both explicit amenity asks and
    descriptor queries ('học bài' -> tag 'học tập') are explained. Pure category
    phrases ('cà phê') are skipped — they describe the class, not the choice.
    Empty when nothing relevant overlaps, so bare name/nav queries gain none."""
    keys = set(qattr)
    for t in normalize_query(query, terms, max_ngram).split():
        if len(t) >= 2 and t not in _REASON_STOP:
            keys.add(t)
    if not keys:
        return []
    cat_phrases = _category_phrases()
    out: list[str] = []
    seen: set[str] = set()
    for a in [*(p.get("attributes") or []), *(p.get("tags") or [])]:
        folded = normalize_query(a, terms, max_ngram)
        if folded in cat_phrases:
            continue  # the category label itself is not a reason
        toks = {t for t in folded.split() if t not in _REASON_STOP}
        if toks & keys and a not in seen:
            seen.add(a)
            out.append(a)
    return out[:5]


# ── Needs: hard filtering + per-need confirmation evidence ──────────────────
# HARD needs (wifi/parking/pool/wc/private_room/charging/24h + price/stars proxy)
# gate candidates; SOFT needs only rank (via the existing _attr_frac lift). A need
# is "confirmed" only when the POI's data shows it — absence is "not_confirmed",
# never a fabricated false. Price/stars are proxied onto ordinal price_level /
# review rating (the corpus has no VND or star fields) and always flagged approx.


def _numeric_need_ok(p: dict, num: dict) -> bool | None:
    """True/False/None(=unknown) for a numeric need against the proxy fields."""
    if num["key"] == "price_max":
        pl = p.get("price_level")
        return None if pl is None else (pl <= 2)
    if num["key"] == "stars":
        r = p.get("rating")
        return None if r is None else (r >= (num.get("value") or 0))
    return None


def _hard_needs_confirmed(p: dict, needs: dict, need_index: dict) -> bool:
    """True iff EVERY hard must_have phrase + numeric need is confirmed by the POI.
    Unknown/absent data ⇒ not confirmed (graceful — the POI drops to the fallback
    set, it is never claimed to satisfy the need)."""
    poi_attrs = p["q"].get("attrs", "")
    for need in needs.get("must_have", []):
        if need_taxonomy.match_need(need["key"], poi_attrs, need_index) is None:
            return False
    for num in needs.get("numeric", []):
        if _numeric_need_ok(p, num) is not True:
            return False
    return True


def _need_evidence(p: dict, needs: dict, need_index: dict) -> list[dict]:
    """Per-need confirmation status for a POI (spec §9/§18): confirmed |
    not_confirmed, with the source field, for every parsed need."""
    poi_attrs = p["q"].get("attrs", "")
    out: list[dict] = []
    for need in [*needs.get("must_have", []), *needs.get("should_have", [])]:
        ph = need_taxonomy.match_need(need["key"], poi_attrs, need_index)
        out.append({
            "need": need["key"], "label": need.get("label_vi") or need["key"],
            "status": "confirmed" if ph else "not_confirmed",
            "source": "attribute" if ph else None,
        })
    for num in needs.get("numeric", []):
        ok = _numeric_need_ok(p, num)
        out.append({
            "need": num["key"],
            "status": "confirmed" if ok is True else "not_confirmed",
            "source": ("price_level" if num["key"] == "price_max" else "rating"),
            "approx": True, "proxy": num.get("proxy"),
        })
    return out


def _has_hard_needs(needs: dict | None) -> bool:
    return bool(needs and (needs.get("must_have") or needs.get("numeric")))


def _apply_need_filter(scored: list, needs: dict | None) -> tuple[list, bool]:
    """Graceful hard-need partition: keep only POIs confirming every hard need; if
    that would empty the (already city/scope-filtered) set, return the original set
    and signal `relaxed=True` so results are labelled not_confirmed rather than
    hidden. Never returns empty when the input had candidates."""
    if not _has_hard_needs(needs):
        return scored, False
    need_index = query_intent.context()["need_index"]
    primary = [(s, p) for s, p in scored if _hard_needs_confirmed(p, needs, need_index)]
    if primary:
        return primary, False
    return scored, True


def _attach_needs(out: dict, p: dict, needs: dict | None) -> dict:
    """Attach per-need confirmation evidence to a result dict (when needs present)."""
    if needs and any(needs.get(k) for k in ("must_have", "should_have", "numeric")):
        need_index = query_intent.context()["need_index"]
        out["matched_needs"] = _need_evidence(p, needs, need_index)
    return out


def _needs_summary(needs: dict | None, relaxed: bool) -> dict | None:
    """Compact query-understanding block for the response (spec §19 geo_contract /
    §22). `hard_relaxed=True` means no POI confirmed all hard needs, so results are
    the graceful fallback (labelled not_confirmed) — not confirmed matches."""
    if not needs or not any(needs.get(k)
                            for k in ("must_have", "should_have", "numeric", "negative")):
        return None
    return {
        "must_have": [n["key"] for n in needs.get("must_have", [])],
        "should_have": [n["key"] for n in needs.get("should_have", [])],
        "numeric": [{"key": n["key"], "value": n.get("value"),
                     "proxy": n.get("proxy"), "approx": True}
                    for n in needs.get("numeric", [])],
        "negative": [n["key"] for n in needs.get("negative", [])],
        "hard_relaxed": relaxed,
    }


def _validation_block(results: list, intent_label: str, geo_contract: dict | None,
                      needs_relaxed: bool) -> dict:
    """Post-search invariants (spec §20), surfaced for observability + the eval
    gates: a coordinate/nearby answer must carry distance on every result, and an
    explicitly-scoped answer must not leak another city. These are already enforced
    by the pipeline; the block makes a violation visible rather than silent."""
    is_geo = intent_label in ("Coordinate Search", "Nearby Search")
    dist_ok = True
    if is_geo and results:
        dist_ok = all("distance_km" in r for r in results)
    return {
        "distance_present": dist_ok,
        "scope_leak": bool((geo_contract or {}).get("multi_city_leak_detected")),
        "needs_relaxed": needs_relaxed,
    }


class MapDbFallback(RuntimeError):
    """Raised (only under ATRIA_MAP_STRICT_DB) when the db engine fails and would
    otherwise silently fall back to JSON — so eval surfaces the degradation."""


def _dispatch(json_impl, db_name: str, args) -> dict:
    """Route to the Postgres engine (search_db) when ATRIA_MAP_BACKEND=db, falling
    back to the JSON engine on ANY db-side failure (stderr warning only — stdout
    shape never changes).

    The fallback is convenient in production but dangerous for evaluation: a
    stopped container or missing driver makes `--backend db` quietly measure the
    JSON engine. Set ATRIA_MAP_STRICT_DB=1 to turn the failure into a hard error
    instead, so eval can never silently degrade."""
    import _db

    if _db.backend() == "db":
        try:
            import search_db

            return getattr(search_db, db_name)(args)
        except Exception as exc:
            if os.environ.get("ATRIA_MAP_STRICT_DB", "").strip().lower() in ("1", "true", "yes"):
                raise MapDbFallback(
                    f"map-db unavailable and ATRIA_MAP_STRICT_DB is set: {exc}") from exc
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
        # Carry the prior brand forward for DISPLAY/labeling only (so the reply can
        # tell exact brand matches apart from same-category fills). Deliberately NOT
        # written to parsed["brands"] — that would re-arm the hard brand filter and
        # drop the related fills the user wants to keep.
        prior_brand = prior.get("brands")
        if isinstance(prior_brand, (list, tuple)):
            prior_brand = prior_brand[0] if prior_brand else None
        if prior_brand:
            parsed["_inherited_brand"] = prior_brand
        # Keep an established opening-hours filter across a city switch ("cafe q1
        # mở sau 9h" -> "tôi ở SG" still means open-after-9pm cafes in HCMC).
        if not parsed.get("time") and prior.get("time"):
            parsed["time"] = prior["time"]
        args.city = parsed["city_entry"]["canonical"]
        return

    # R3: an opening-hours-only refinement ("còn mở cửa không?", "sau 9h tối") with
    # no subject of its own inherits the prior category (+ city) and re-runs it with
    # the new hours filter — so the user can narrow the same list by time.
    if (parsed.get("time") and prior_cat and not parsed.get("category")
            and not parsed.get("brands") and parsed.get("city_entry") is None
            and parsed.get("coords") is None and parsed.get("anchor_text") is None
            and parsed.get("anchor_coords") is None):
        parsed["category"] = prior_cat
        args.category = prior_cat
        parsed["intent"] = "category"
        parsed["_inherited"] = True
        if prior_city and not getattr(args, "city", None):
            args.city = prior_city
            entry = _city_entry_for(prior_city)
            if entry is not None:
                parsed["city_entry"] = entry
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

    # "tọa độ/địa chỉ của <POI>" — score the clean extracted name, not the raw
    # wrapper ("toa do cua ... la gi"), whose extra tokens dilute the POI below
    # threshold. Re-dispatch on the wrapper-free name, then restamp the lookup
    # action from this authoritative parse (the re-parse of the bare name won't
    # re-detect it). Mirrors the bare "chợ bến thành" search, which resolves fine.
    if parsed.get("coord_lookup_name"):
        original_q = args.query
        args.query = parsed["coord_lookup_name"]
        try:
            resp = _dispatch(_cmd_search_json, "cmd_search_db", args)
        finally:
            args.query = original_q
        resp["query"] = original_q
        resp["intent"] = query_intent.competition_intent(parsed)
        resp["entities"] = parsed["entities"]
        return resp

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
    # Geometric intents answer with a specialized retrieval; if it comes back
    # EMPTY (nav destination absent from the dataset, "gần <landmark>" where the
    # landmark doesn't resolve, e.g. "resort gần biển", "đi đâu với trẻ em"), fall
    # through to the plain engine below rather than returning nothing. The plain
    # engine still re-derives + applies the detected city/category, so precision
    # (city filter) is preserved — only the proximity/nav constraint is dropped,
    # letting hybrid vector recall answer the open-ended discovery query. Explicit
    # coordinate intents never fall back (the point is unambiguous).
    if intent == "navigation" and parsed["destination_text"]:
        nav = _navigation_response(args, parsed, categories, pois, terms, max_ngram)
        if nav.get("count"):
            return nav
    elif intent == "nearby" and (parsed["anchor_text"] or parsed["anchor_coords"] is not None):
        addresses = load_json("addresses.json")["addresses"]
        anchor_city = parsed["city_entry"]["canonical"] if parsed["city_entry"] else None
        anchor = _resolve_anchor(parsed, pois, addresses, terms, max_ngram, city=anchor_city)
        if anchor is not None:
            anc = _anchored_response(args, parsed, pois,
                                     (anchor["lat"], anchor["lng"]), anchor)
            if anc.get("count"):
                return anc
        # anchor unresolved or nothing near it -> plain, city-filtered search

    resp = _dispatch(_cmd_search_json, "cmd_search_db", args)
    if parsed.get("_inherited"):
        # The plain engines re-parse the raw text internally, so a follow-up like
        # "toi o SG" re-derives its nav misfire there and mislabels the response.
        # Restamp the intent from the authoritative merged parse.
        resp["intent"] = query_intent.competition_intent(parsed)
        # Inherited brand: tag which results are the real brand and which are
        # same-category fills, and surface a display label — so the interactive
        # reply can list the exact matches first and label the extras. Only ever
        # runs on the interactive multi-turn path (args.prior set); the bench/eval
        # never set prior, so resp is untouched for them.
        ib = parsed.get("_inherited_brand")
        if ib:
            tok = fold(ib)
            poi_by_id = {p["poi_id"]: p for p in pois}
            label = None
            for r in resp.get("results") or []:
                p = poi_by_id.get(r["poi_id"])
                hit = bool(p and _brand_hit([tok], p))
                r["is_brand_match"] = hit
                if hit and label is None and p.get("brand"):
                    label = p["brand"]
            resp["inherited_brand"] = label or str(ib).title()
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
    # Nearby + needs: within the radius, keep only POIs confirming every hard need
    # (distance stays the primary ranking within the confirmed set); graceful — if
    # none confirm, keep the distance-ranked set tagged not_confirmed.
    needs = parsed.get("needs") or {}
    rows, needs_relaxed = _apply_need_filter(rows, needs)
    top = rows[: args.limit]
    intent_label = query_intent.competition_intent(parsed)
    # Amenity matches also annotate the reason ("cafe có wifi gần hồ gươm" -> wifi).
    qattr = set(parsed.get("attr_tokens") or [])
    r_terms, r_ngram = load_abbreviations()
    results = [
        _attach_needs(
            _public(p, distance_km=d,
                    reasons=_match_reasons(p, qattr, args.query, r_terms, r_ngram)),
            p, needs)
        for d, p in top
    ]
    resp_city = parsed["city_entry"]["canonical"] if parsed["city_entry"] else None
    geo_contract = _geo_contract(resp_city, None, anchor, results)
    return {
        "query": args.query,
        "normalized_query": parsed["normalized_query"],
        "category": category,
        "city": resp_city,
        "intent": intent_label,
        "anchor": anchor,
        "place_scope": None,
        "geo_contract": geo_contract,
        "entities": parsed["entities"],
        "needs": _needs_summary(needs, needs_relaxed),
        "validation": _validation_block(results, intent_label, geo_contract, needs_relaxed),
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
    qattr = set(parsed.get("attr_tokens") or [])  # amenity ranking signal
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
            # category query: score the remainder as a location/name constraint,
            # and lift by amenity match ("quán cà phê YÊN TĨNH ĐỂ LÀM VIỆC") — all
            # three share the 55..90 band so the score scale/thresholds are intact.
            loc = _location_score(remainder, p)
            rem_name = _score_text(remainder, _poi_keys(p)) if remainder else 0
            cat_s = 55 + 35 * max(loc, rem_name / 100, _attr_frac(qattr, p))
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
            scored.append((s + _popularity_bonus(p), p))

    # Sub-city scope: keep only results in a named district/street when present.
    scored, scope_note = _apply_scope(scored, norm)
    # Graceful hard-need filter: keep only POIs confirming every hard need; if that
    # empties the (city/scope-filtered) set, fall back to the full set tagged
    # not_confirmed so we never return empty when the area has category matches.
    needs = parsed.get("needs") or {}
    scored, needs_relaxed = _apply_need_filter(scored, needs)
    scored.sort(key=lambda t: -t[0])
    top = scored[: args.limit]
    # The intent stays as parsed even when a landmark anchor failed to resolve:
    # the USER intent is still a nearby search; only the retrieval degraded (to a
    # plain, city-filtered search) — disclosed by anchor=null.
    intent_label = query_intent.competition_intent(parsed)
    results = [
        _attach_needs(
            _public(p, score=s, reasons=_match_reasons(p, qattr, args.query, terms, max_ngram)),
            p, needs)
        for s, p in top
    ]
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
        "needs": _needs_summary(needs, needs_relaxed),
        "validation": _validation_block(results, intent_label,
                                        _geo_contract(eff_city, scope_note, None, results),
                                        needs_relaxed),
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
