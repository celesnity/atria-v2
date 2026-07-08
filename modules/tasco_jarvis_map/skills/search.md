---
name: search
description: Full reference for search.py — subcommands, flags, JSON output shapes, and normalization behavior.
---

# search.py reference

Run from anywhere with an absolute path; each subcommand prints one JSON
object to stdout (`ensure_ascii`, exit 0 — soft failures return `{"error"}`).

## Normalization (applies to `search` and `geocode` queries)

1. lowercase, collapse whitespace; 2. strip Vietnamese diacritics (đ→d);
3. expand abbreviations longest-n-gram-first from the dataset dictionary
   (q1→quan 1, tp hcm→thanh pho ho chi minh, nvl→nguyen van linh, …).

Dataset keys were pre-folded and pre-expanded the same way at ingest, so
"vincom q1", "Vincom Quận 1" and "vincom quan 1" all match.

## Subcommands

### `search "<query>" [--limit 8] [--city <folded>] [--category <key>]`
Category-aware POI search. Detects a category phrase inside the query
("cafe", "nha thuoc", "tram sac"…), uses leftover tokens as a
district/city/name constraint.
Output: `{query, normalized_query, category, results: [...], count}`;
each result: `{poi_id, name, name_en, category, lat, lng, address,
district, city, rating, opening_hours, score}` (score 0–100, sorted desc).

### `near --lat <f> --lng <f> [--radius-km 3] [--category <key>] [--limit 8]`
Haversine radius search, sorted by distance.
Output adds `distance_km` per result and echoes `origin`/`radius_km`.

### `geocode "<query>"`
Best coordinate match across the address dataset (150 rows) and POIs.
Output: `{match: {kind: "address"|"poi", id, name, lat, lng, full_address},
score, alternates: [up to 3]}`; `match` is null when nothing scores > 20.

### `pois [--city <folded>] [--category <key>]`
Full enriched dump for the dashboard: `{categories, pois, count,
abbreviations}`.

### `categories`
`{categories: {key: {label, label_vi, color, emoji}}, counts: {key: n}}`.
Category keys: cafe, restaurant, hotel, supermarket, convenience, mall,
bank, cinema, hospital, pharmacy, gas, ev_charging, electronics, airport,
bus_station, market, attraction.

## Quality baseline

`scripts/eval.py` vs the 60 public evaluation queries: poi_hit@1 100%
(11/11 answerable), category detection 100% (34/34). Three eval queries
target POIs absent from the participants dataset (coverage gaps).
