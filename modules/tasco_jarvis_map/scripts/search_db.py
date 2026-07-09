"""Postgres (GeoRAG) engine for the map CLI — hybrid retrieval, legacy shapes.

Each cmd_*_db mirrors its search.py counterpart's OUTPUT SHAPE exactly (the
dashboard, jarvis_chat and eval depend on it). Rows come back with the
verbatim `raw` jsonb (the original dataset object), so every emitted field is
byte-identical to the JSON engine; the DB adds retrieval signals on top:

  s_lex  — legacy tier scoring (exact/prefix/substring/token-overlap, reused
           from search.py on raw["q"]) fused with pg_trgm similarity over
           normalized_name / name_blob / aliases (rank>0 penalized)
  s_fts  — ts_rank_cd over the generated 'simple' tsvector, saturated to 0..1
  s_vec  — pgvector exact cosine vs the OpenAI query embedding (cached in
           map_query_embeddings; absent key/error -> signal dropped)
  s_geo  — PostGIS distance decay (only when an origin is provided)

final score = 100 * max(fused, legacy/100), preserving the legacy 0-100 scale
(threshold >20, jarvis fast-path >=55) — hybrid adds recall, never loses a
legacy match.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db
import gazetteer
import query_intent
from _data import fold, load_abbreviations, normalize_query

# Legacy scoring/detection helpers stay the single source of truth.
# search_db is only imported lazily from inside search.py's cmd_* wrappers
# (or standalone), so this import is not circular.
from search import (
    _apply_scope,
    _brand_hit,
    _category_index,
    _confidence,
    _coverage_score,
    _detect_category,
    _geo_contract,
    _location_score,
    _now_minutes,
    _parse_with_flags,
    _poi_keys,
    _public,
    _score_text,
    _strip_noise,
    _time_ok,
)

_GAZ = None


def _gazetteer_db(conn) -> dict:
    """Place gazetteer loaded from map_admin_areas (populated by db_import.py).
    Falls back to deriving it from the JSON files when the table is empty
    (pre-migration DB) — city filtering must never crash a search."""
    global _GAZ
    if _GAZ is None:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT level, canonical, name, parent_city, variant, source "
                "FROM map_admin_areas"
            )
            rows = cur.fetchall()
        if rows:
            ents: dict = {}
            entries = []
            for level, canonical, name, parent, variant, source in rows:
                key = (level, canonical)
                if key not in ents:
                    ents[key] = {
                        "level": level,
                        "canonical": canonical,
                        "name": name,
                        "parent_city": parent,
                        "variants": {},
                    }
                    entries.append(ents[key])
                ents[key]["variants"][variant] = source
            city_idx: dict = {}
            for e in entries:
                if e["level"] == "city":
                    for v in e["variants"]:
                        city_idx.setdefault(v, e)
            _GAZ = {"entries": entries, "city_idx": city_idx}
        else:
            _GAZ = gazetteer.build_from_data()
    return _GAZ


def _embed_query(conn, query: str):
    """Query embedding via the map_query_embeddings cache; None disables s_vec."""
    if _db.embed_disabled():
        return None
    api_key = _db.env_get("OPENAI_API_KEY")
    if not api_key:
        return None
    model = _db.EMBED_MODEL
    qhash = hashlib.sha256((model + "\0" + query).encode("utf-8")).hexdigest()
    with conn.cursor() as cur:
        cur.execute("SELECT embedding FROM map_query_embeddings WHERE query_hash=%s", (qhash,))
        row = cur.fetchone()
        if row:
            vec = row[0]  # pgvector Vector (no numpy) or ndarray (with numpy)
            return vec.to_list() if hasattr(vec, "to_list") else list(vec)
        try:
            from openai import OpenAI

            resp = OpenAI(api_key=api_key).embeddings.create(model=model, input=[query])
            vec = resp.data[0].embedding
        except Exception as exc:  # embed failure must never fail the search
            print(f"WARN query embedding skipped: {exc}", file=sys.stderr)
            return None
        cur.execute(
            """INSERT INTO map_query_embeddings (query_hash, query_text, embedding, model)
               VALUES (%s, %s, %s, %s) ON CONFLICT (query_hash) DO NOTHING""",
            (qhash, query, vec, model),
        )
        return vec


def _fuse(signals: dict[str, float | None], origin: bool) -> float:
    """Weighted fusion over the available (non-None) signals, renormalized."""
    weights = _db.WEIGHTS_ORIGIN if origin else _db.WEIGHTS_NO_ORIGIN
    total = sum(w for k, w in weights.items() if signals.get(k) is not None and w > 0)
    if total <= 0:
        return 0.0
    return (
        sum(w * signals[k] for k, w in weights.items() if signals.get(k) is not None and w > 0)
        / total
    )


def _db_categories(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT key, label, label_vi, color, emoji FROM map_categories")
        return {
            k: {"label": lb, "label_vi": lv, "color": c, "emoji": e}
            for k, lb, lv, c, e in cur.fetchall()
        }


_POI_SIGNAL_SQL = """
SELECT p.raw,
       greatest(similarity(p.normalized_name, %(norm)s),
                similarity(p.normalized_name, %(raw)s))              AS trgm_name,
       greatest(word_similarity(%(norm)s, p.name_blob),
                word_similarity(%(raw)s, p.name_blob))               AS trgm_blob,
       coalesce((SELECT max(greatest(similarity(a.normalized_alias, %(norm)s),
                                     similarity(a.normalized_alias, %(raw)s))
                            - CASE WHEN a.rank > 0 THEN {pen} ELSE 0 END)
                 FROM map_aliases a
                 WHERE a.entity_type = 'poi' AND a.entity_id = p.poi_id), 0) AS trgm_alias,
       ts_rank_cd(p.fts, websearch_to_tsquery('simple', %(norm)s), 32)       AS fts_rank,
       {vec_expr}                                                            AS vec_sim
FROM map_pois p
"""


def _poi_signal_rows(conn, norm: str, raw: str, qvec) -> list[dict]:
    vec_expr = (
        "(SELECT 1 - (e.embedding <=> %(qvec)s::vector) FROM map_embeddings e "
        "WHERE e.entity_type = 'poi' AND e.entity_id = p.poi_id)"
        if qvec is not None
        else "NULL"
    )
    sql = _POI_SIGNAL_SQL.format(pen=_db.ALIAS_PENALTY, vec_expr=vec_expr)
    params = {"norm": norm, "raw": raw, "qvec": qvec}
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {
                "raw": r[0],
                "trgm": max(r[1] or 0.0, r[2] or 0.0, r[3] or 0.0),
                "fts": min(1.0, (r[4] or 0.0) / _db.FTS_SATURATION),
                "vec": (max(0.0, min(1.0, float(r[5]))) if r[5] is not None else None),
            }
            for r in cur.fetchall()
        ]


def _search_pipeline(conn, query: str, city: str | None, category: str | None,
                     parsed: dict | None = None, now_min: int = 720) -> dict:
    """Shared scoring pipeline for cmd_search_db and cmd_explain_match_db.

    Returns {norm, cat_key, remainder, kept, all}: `kept` is the ranked list
    of rows above threshold (sort key = score + rating/100, legacy tiebreak);
    `all` keeps every row with its full signal breakdown for explain. `parsed`
    is the query_intent router output (brands / time); when None it is derived
    here (explain path). Geometric intents never reach this pipeline — they are
    resolved upstream in search.cmd_search over the JSON data (both backends)."""
    terms, max_ngram = load_abbreviations()
    raw_q = fold(query)
    norm = normalize_query(query, terms, max_ngram)
    gaz = _gazetteer_db(conn)
    if parsed is None:
        cat_idx0 = _category_index(_db_categories(conn))
        parsed = query_intent.parse(query, query_intent.context(), _detect_category, cat_idx0)
    # Place pre-pass (mirrors the json engine): detect a data-derived city
    # mention, strip it + noise from the category/location string; name
    # scoring keeps the full norm/raw.
    place, rest = gazetteer.detect_place(norm, gaz)
    rest = _strip_noise(rest)
    cat_idx = _category_index(_db_categories(conn))
    cat_key, remainder = _detect_category(rest, cat_idx)
    if category:
        cat_key = category
    eff_city = (
        gazetteer.resolve_place(city, gaz) if city else (place["canonical"] if place else None)
    )
    brands = parsed["brands"]
    brand_remainder = parsed["remainder"]

    qvec = _embed_query(conn, query)
    rows = _poi_signal_rows(conn, norm, raw_q, qvec)

    # Brand + category = hard brand filter (mirror of the json engine): only
    # applied when the brand actually has a POI in that category.
    brand_filter = bool(brands) and bool(cat_key) and any(
        r["raw"]["category"] == cat_key and _brand_hit(brands, r["raw"]) for r in rows
    )

    detailed: list[dict] = []
    for row in rows:
        p = row["raw"]
        if eff_city and eff_city not in fold(p["city"]):
            continue  # HARD city filter — precision over recall
        if not _time_ok(p, parsed["time"], now_min):
            continue  # opening-hours constraint from the router
        if brand_filter and not _brand_hit(brands, p):
            continue  # named-brand precision
        keys = _poi_keys(p)
        legacy = max(
            _score_text(norm, keys),
            _score_text(raw_q, keys) if raw_q != norm else 0,
            _coverage_score(norm, p),
        )
        s_lex = max(legacy / 100.0, row["trgm"])
        signals = {"lex": s_lex, "fts": row["fts"], "vec": row["vec"]}
        fused = _fuse(signals, origin=False)
        name_s = 100.0 * max(fused, legacy / 100.0)

        branch = "name"
        loc = None
        if cat_key and p["category"] == cat_key:
            loc = _location_score(remainder, p)
            rem_name = _score_text(remainder, keys) if remainder else 0
            cat_s = 55 + 35 * max(loc, rem_name / 100)
            s = max(name_s, cat_s)
            branch = "category_match"
        elif cat_key:
            # off-category for a CATEGORY search: keep only near-exact NAME matches;
            # everything else is noise (precision > recall). Mirrors search.py.
            s = name_s * 0.5 if name_s >= 80 else 0.0
            branch = "off_category_drop"
        else:
            s = name_s
        if brands and _brand_hit(brands, p):
            rem_name = _score_text(brand_remainder, keys) / 100 if brand_remainder else 0.0
            brand_s = 58 + 34 * rem_name
            if brand_s > s:
                s = brand_s
                branch = "brand"
        detailed.append(
            {
                "poi": p,
                "score": s,
                "sort_key": s + (p["rating"] or 0) / 100,
                "kept": s > _db.SCORE_THRESHOLD,
                "signals": {**signals, "trgm": row["trgm"], "legacy": legacy, "loc": loc},
                "fused": fused,
                "branch": branch,
            }
        )

    kept = sorted((d for d in detailed if d["kept"]), key=lambda d: -d["sort_key"])
    return {
        "norm": norm,
        "cat_key": cat_key,
        "remainder": remainder,
        "city": eff_city,
        "kept": kept,
        "all": detailed,
        "has_vec": qvec is not None,
    }


def cmd_search_db(args) -> dict:
    conn = _db.connect()
    now_min = _now_minutes(args)
    with conn:
        categories = _db_categories(conn)
        terms, max_ngram = load_abbreviations()
        parsed = _parse_with_flags(args, categories, terms, max_ngram)
        pipe = _search_pipeline(conn, args.query, args.city, args.category, parsed, now_min)
    # Sub-city scope filter (mirror of the json engine): keep only in-district /
    # in-street results when any exist, else disclose via place_scope.
    scored = [(d["sort_key"], d["poi"]) for d in pipe["kept"]]
    scored, scope_note = _apply_scope(scored, pipe["norm"])
    top = scored[: args.limit]
    intent_label = query_intent.competition_intent(parsed)
    results = [_public(p, score=s) for s, p in top]
    return {
        "query": args.query,
        "normalized_query": pipe["norm"],
        "category": pipe["cat_key"],
        "city": pipe["city"],
        "intent": intent_label,
        "anchor": None,
        "place_scope": scope_note,
        "geo_contract": _geo_contract(pipe["city"], scope_note, None, results),
        "entities": parsed["entities"],
        "confidence_score": _confidence(intent_label, results, None),
        "results": results,
        "count": len(top),
    }


def cmd_near_db(args) -> dict:
    conn = _db.connect()
    with conn, conn.cursor() as cur:
        cur.execute(
            """SELECT raw, ST_Distance(geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography) AS m
               FROM map_pois
               WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography, %(radius_m)s)
                 AND (%(cat)s::text IS NULL OR category = %(cat)s)
               ORDER BY m
               LIMIT %(limit)s""",
            {
                "lat": args.lat,
                "lng": args.lng,
                "radius_m": args.radius_km * 1000.0,
                "cat": args.category,
                "limit": args.limit,
            },
        )
        rows = cur.fetchall()
    return {
        "origin": {"lat": args.lat, "lng": args.lng},
        "radius_km": args.radius_km,
        "category": args.category,
        "results": [_public(p, distance_km=m / 1000.0) for p, m in rows],
        "count": len(rows),
    }


def cmd_geocode_db(args) -> dict:
    conn = _db.connect()
    with conn:
        terms, max_ngram = load_abbreviations()
        norm = normalize_query(args.query, terms, max_ngram)
        qvec = _embed_query(conn, args.query)

        cands: list[tuple[float, str, dict]] = []

        vec_expr = (
            "(SELECT 1 - (e.embedding <=> %(qvec)s::vector) FROM map_embeddings e "
            "WHERE e.entity_type = 'address' AND e.entity_id = a.address_id)"
            if qvec is not None
            else "NULL"
        )
        with conn.cursor() as cur:
            cur.execute(
                f"""SELECT a.raw,
                           similarity(a.normalized_full, %(norm)s) AS trgm_full,
                           coalesce((SELECT max(similarity(al.normalized_alias, %(norm)s)
                                                - CASE WHEN al.rank > 0 THEN {_db.ALIAS_PENALTY} ELSE 0 END)
                                     FROM map_aliases al
                                     WHERE al.entity_type = 'address'
                                       AND al.entity_id = a.address_id), 0) AS trgm_alias,
                           ts_rank_cd(a.fts, websearch_to_tsquery('simple', %(norm)s), 32) AS fts_rank,
                           {vec_expr} AS vec_sim
                    FROM map_addresses a""",
                {"norm": norm, "qvec": qvec},
            )
            for raw, trgm_full, trgm_alias, fts_rank, vec_sim in cur.fetchall():
                keys = [raw["q"]["full"], *raw["q"]["aliases"]]
                legacy = _score_text(norm, keys)
                s_lex = max(legacy / 100.0, trgm_full or 0.0, trgm_alias or 0.0)
                fused = _fuse(
                    {
                        "lex": s_lex,
                        "fts": min(1.0, (fts_rank or 0.0) / _db.FTS_SATURATION),
                        "vec": (
                            max(0.0, min(1.0, float(vec_sim))) if vec_sim is not None else None
                        ),
                    },
                    origin=False,
                )
                s = 100.0 * max(fused, legacy / 100.0)
                if s > _db.SCORE_THRESHOLD:
                    cands.append((s, "address", raw))

        for row in _poi_signal_rows(conn, norm, norm, qvec):
            p = row["raw"]
            legacy = _score_text(norm, _poi_keys(p))
            s_lex = max(legacy / 100.0, row["trgm"])
            fused = _fuse({"lex": s_lex, "fts": row["fts"], "vec": row["vec"]}, origin=False)
            s = 100.0 * max(fused, legacy / 100.0)
            if s > _db.SCORE_THRESHOLD:
                cands.append((s, "poi", p))

    cands.sort(key=lambda t: -t[0])
    if not cands:
        return {"query": args.query, "normalized_query": norm, "match": None, "alternates": []}

    def pub(kind: str, row: dict) -> dict:
        if kind == "poi":
            return {
                "kind": "poi",
                "id": row["poi_id"],
                "name": row["name"],
                "lat": row["lat"],
                "lng": row["lng"],
                "full_address": row["address"],
            }
        return {
            "kind": "address",
            "id": row["address_id"],
            "name": row["full_address"],
            "lat": row["lat"],
            "lng": row["lng"],
            "full_address": row["full_address"],
        }

    best = cands[0]
    return {
        "query": args.query,
        "normalized_query": norm,
        "match": pub(best[1], best[2]),
        "score": round(best[0], 1),
        "alternates": [pub(k, r) for _, k, r in cands[1:4]],
    }


def cmd_pois_db(args) -> dict:
    conn = _db.connect()
    with conn, conn.cursor() as cur:
        terms, max_ngram = load_abbreviations()
        categories = _db_categories(conn)
        city = gazetteer.resolve_place(args.city, _gazetteer_db(conn)) if args.city else None
        cur.execute(
            """SELECT raw FROM map_pois
               WHERE (%(cat)s::text IS NULL OR category = %(cat)s)
               ORDER BY poi_id""",
            {"cat": args.category},
        )
        rows = [r[0] for r in cur.fetchall()]
    if city:
        rows = [p for p in rows if city in fold(p["city"])]
    return {
        "categories": categories,
        "pois": rows,
        "count": len(rows),
        "abbreviations": {"terms": terms, "max_ngram": max_ngram},
    }


def cmd_categories_db(args) -> dict:
    conn = _db.connect()
    with conn, conn.cursor() as cur:
        categories = _db_categories(conn)
        cur.execute("SELECT category, count(*) FROM map_pois GROUP BY category")
        counts = {k: n for k, n in cur.fetchall()}
    return {"categories": categories, "counts": counts}


# ---------------------------------------------------------------------------
# GeoRAG-only tools (no JSON-engine counterpart): reverse_geocode,
# find_duplicates, explain_match.
# ---------------------------------------------------------------------------

REVERSE_AMBIGUOUS_M = 25.0  # top-2 candidates closer than this -> "ambiguous"
REVERSE_NOT_FOUND_M = 2000.0  # nearest beyond this -> "not_found"


def cmd_reverse_geocode_db(args) -> dict:
    """Nearest known place/address for a coordinate (PostGIS KNN over both tables)."""
    conn = _db.connect()
    with conn, conn.cursor() as cur:
        cur.execute(
            """SELECT kind, id, name, full_address, lat, lng,
                      ST_Distance(geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography) AS m
               FROM (
                   SELECT 'poi'::text AS kind, poi_id AS id, name,
                          address AS full_address, lat, lng, geom FROM map_pois
                   UNION ALL
                   SELECT 'address', address_id, full_address,
                          full_address, lat, lng, geom FROM map_addresses
               ) u
               ORDER BY m
               LIMIT %(limit)s""",
            {"lat": args.lat, "lng": args.lng, "limit": args.limit},
        )
        rows = [
            {
                "kind": k,
                "id": i,
                "name": n,
                "full_address": fa,
                "lat": lat,
                "lng": lng,
                "distance_m": round(m, 1),
            }
            for k, i, n, fa, lat, lng, m in cur.fetchall()
        ]

    if not rows or rows[0]["distance_m"] > REVERSE_NOT_FOUND_M:
        status = "not_found"
        match, alternates = None, rows
    else:
        match, alternates = rows[0], rows[1:]
        status = "success"
        if alternates and alternates[0]["distance_m"] - match["distance_m"] < REVERSE_AMBIGUOUS_M:
            status = "ambiguous"
    return {
        "origin": {"lat": args.lat, "lng": args.lng},
        "match": match,
        "alternates": alternates,
        "status": status,
    }


# Duplicate-pair weights (phone weight from the reference blueprint dropped —
# the dataset has no phone field). Thresholds: >=0.90 duplicate, >=--threshold
# (default 0.75) possible.
DUP_WEIGHTS = {"name": 0.45, "address": 0.25, "distance": 0.20, "category": 0.10}


def cmd_find_duplicates_db(args) -> dict:
    """Score POI pairs within --radius-m for likely duplication."""
    conn = _db.connect()
    with conn, conn.cursor() as cur:
        cur.execute(
            """SELECT a.poi_id, a.name, b.poi_id, b.name,
                      similarity(a.normalized_name, b.normalized_name) AS name_sim,
                      similarity(coalesce(a.normalized_address, ''),
                                 coalesce(b.normalized_address, '')) AS addr_sim,
                      ST_Distance(a.geom, b.geom) AS m,
                      (a.category = b.category)::int AS same_cat
               FROM map_pois a
               JOIN map_pois b ON a.poi_id < b.poi_id
                AND ST_DWithin(a.geom, b.geom, %(radius_m)s)""",
            {"radius_m": args.radius_m},
        )
        pairs = []
        for a_id, a_name, b_id, b_name, name_sim, addr_sim, m, same_cat in cur.fetchall():
            signals = {
                "name_similarity": round(float(name_sim or 0), 3),
                "address_similarity": round(float(addr_sim or 0), 3),
                "distance_m": round(m, 1),
                "distance_decay": round(max(0.0, 1.0 - m / args.radius_m), 3),
                "same_category": bool(same_cat),
            }
            score = (
                DUP_WEIGHTS["name"] * signals["name_similarity"]
                + DUP_WEIGHTS["address"] * signals["address_similarity"]
                + DUP_WEIGHTS["distance"] * signals["distance_decay"]
                + DUP_WEIGHTS["category"] * same_cat
            )
            if score >= args.threshold:
                pairs.append(
                    {
                        "poi_a": {"id": a_id, "name": a_name},
                        "poi_b": {"id": b_id, "name": b_name},
                        "score": round(score, 3),
                        "signals": signals,
                        "verdict": "duplicate" if score >= 0.90 else "possible",
                    }
                )
    pairs.sort(key=lambda x: -x["score"])
    return {
        "threshold": args.threshold,
        "radius_m": args.radius_m,
        "pairs": pairs,
        "count": len(pairs),
    }


def cmd_explain_match_db(args) -> dict:
    """Full hybrid-signal breakdown for one POI under a query — debug workhorse."""
    conn = _db.connect()
    with conn:
        pipe = _search_pipeline(conn, args.query, None, None)
        target = next((d for d in pipe["all"] if d["poi"]["poi_id"] == args.poi_id), None)
        if target is None:
            # Not in the pipeline: either the id doesn't exist, or the hard
            # city filter excluded it before scoring — say which (a debug tool
            # must not call an existing POI "unknown").
            with conn.cursor() as cur:
                cur.execute("SELECT name, city FROM map_pois WHERE poi_id = %s", (args.poi_id,))
                row = cur.fetchone()
            if row is None:
                return {"error": f"unknown poi_id: {args.poi_id}"}
            return {
                "query": args.query,
                "normalized_query": pipe["norm"],
                "category": pipe["cat_key"],
                "city": pipe["city"],
                "poi_id": args.poi_id,
                "poi_name": row[0],
                "poi_city": row[1],
                "excluded_by": "city_filter",
                "score": 0.0,
                "rank_in_results": None,
                "above_threshold": False,
            }
    rank = next(
        (i + 1 for i, d in enumerate(pipe["kept"]) if d["poi"]["poi_id"] == args.poi_id), None
    )
    sig = target["signals"]
    return {
        "query": args.query,
        "normalized_query": pipe["norm"],
        "category": pipe["cat_key"],
        "city": pipe["city"],
        "remainder": pipe["remainder"],
        "poi_id": args.poi_id,
        "poi_name": target["poi"]["name"],
        "signals": {
            "lex": round(sig["lex"], 3),
            "fts": round(sig["fts"], 3),
            "vec": (round(sig["vec"], 3) if sig["vec"] is not None else None),
            "trgm": round(sig["trgm"], 3),
            "legacy": round(sig["legacy"], 1),
            "loc": (round(sig["loc"], 3) if sig["loc"] is not None else None),
        },
        "weights": _db.WEIGHTS_NO_ORIGIN,
        "vector_signal_active": pipe["has_vec"],
        "branch": target["branch"],
        "fused": round(target["fused"], 3),
        "score": round(target["score"], 1),
        "rank_in_results": rank,
        "above_threshold": target["kept"],
    }
