"""Additive ingest: AI Maps Track-2 xlsx -> merge into data/pois.json.

The Track-2 workbook is a SEPARATE, richer corpus (IDs ``C001+``, no id/name overlap
with the Track-1 190) that carries the enrichment fields Track-1 lacks: per-POI
``attributes``/``tags``/``description`` and ``popularity_score``/``review_count``/
``price_level``/``sub_category``. This script is **additive and idempotent**:

  1. load the committed data/pois.json (Track-1 output of ingest.py);
  2. backfill the new optional fields on every legacy POI (-> null/empty);
  3. build the Track-2 POIs with those fields populated + a synthesized ``q{}`` block
     (city labels normalized to the Track-1 canonical forms so the data-derived
     gazetteer does not split a city in two);
  4. union (Track-2 replaces any prior C-rows on re-run) and rewrite pois.json.

It also writes:
  data/eval_track2.json        the Track-2 Public_Evaluation (semantic/ranking gold)
  data/attribute_taxonomy.json the canonical amenity vocabulary (10 attributes)

Usage (repo venv, PYTHONUTF8=1):
  python scripts/ingest_track2.py \
    --xlsx "D:\\[Challenge]_GenaiFund\\[Project]_MapMinder\\Dataset_Map_Track1-7\\ai_maps_track2_dataset_participants.xlsx"

Re-run only when the Track-2 dataset version changes; pois.json is committed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import DATA_DIR, expand_abbrev, fold, load_abbreviations  # noqa: E402
from ingest import CATEGORIES, RAW_TO_KEY, _s, _sheet_dicts, _write  # noqa: E402

# Track-2 city labels -> the exact display strings the Track-1 190 already use, so
# the gazetteer (derived from POI ``city`` values) keeps one canonical per city.
CITY_CANON = {
    "TP.HCM": "TP Hồ Chí Minh",
    "TPHCM": "TP Hồ Chí Minh",
    "TP HCM": "TP Hồ Chí Minh",
    "Hồ Chí Minh": "TP Hồ Chí Minh",
    "Hà Nội": "Hà Nội",
    "Đà Nẵng": "Đà Nẵng",
    "Đà Lạt": "Đà Lạt",  # new city — no prior canonical; keep as-is
}

# The new optional enrichment fields, with their empty/absent value. Legacy 190
# POIs get these so the schema is uniform across the union.
_ENRICH_EMPTY = {
    "sub_category": "",
    "attributes": [],
    "tags": [],
    "description": "",
    "popularity_score": None,
    "review_count": None,
    "price_level": None,
}


def _semis(raw) -> list[str]:
    return [t.strip() for t in _s(raw).replace(",", ";").split(";") if t.strip()]


def _int(v):
    try:
        return int(float(_s(v)))
    except (ValueError, TypeError):
        return None


def _rating(v):
    try:
        return round(float(_s(v)), 1)
    except (ValueError, TypeError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", required=True, help="path to the Track-2 participants xlsx")
    args = ap.parse_args()

    import openpyxl  # repo venv dependency

    terms, max_ngram = load_abbreviations()

    def xfold(text) -> str:
        return expand_abbrev(fold(text), terms, max_ngram)

    # --- existing corpus -----------------------------------------------------
    with open(DATA_DIR / "pois.json", encoding="utf-8") as fh:
        doc = json.load(fh)
    categories: dict = doc["categories"]
    # Keep only the Track-1 legacy corpus (ids ``POI###``); drop any Track-2 rows
    # from a previous run so re-ingest is idempotent (Track-2 ids are prefixed by
    # category letter — C/R/H/M/A/G/... — not a single fixed letter).
    pois = [p for p in doc["pois"] if p["poi_id"].startswith("POI")]
    # Backfill the enrichment fields on the legacy corpus.
    for p in pois:
        for k, empty in _ENRICH_EMPTY.items():
            p.setdefault(k, list(empty) if isinstance(empty, list) else empty)
        p["q"].setdefault("attrs", "")

    wb = openpyxl.load_workbook(args.xlsx, read_only=True)

    # --- Track-2 POIs --------------------------------------------------------
    added = []
    for d in _sheet_dicts(wb, "POI_Dataset"):
        raw_cat = _s(d["category"])
        key = RAW_TO_KEY.get(raw_cat, "other")
        city = CITY_CANON.get(_s(d["city"]), _s(d["city"]))
        name = _s(d["poi_name"])
        attributes = _semis(d.get("attributes"))
        tags = _semis(d.get("tags"))
        addr = f"{_s(d['address'])} {_s(d['district'])} {city}"
        added.append({
            "poi_id": _s(d["poi_id"]),
            "name": name,
            "name_en": "",
            "category": key,
            "category_raw": raw_cat,
            "brand": _s(d["brand"]),
            "address": _s(d["address"]),
            "district": _s(d["district"]),
            "city": city,
            "lat": float(d["latitude"]),
            "lng": float(d["longitude"]),
            "aliases": [],
            "opening_hours": _s(d["opening_hours"]),
            "rating": _rating(d["rating"]),
            "sub_category": _s(d.get("sub_category")),
            "attributes": attributes,
            "tags": tags,
            "description": _s(d.get("description")),
            "popularity_score": _int(d.get("popularity_score")),
            "review_count": _int(d.get("review_count")),
            "price_level": _int(d.get("price_level")),
            "q": {
                "name": xfold(name),
                "name_en": "",
                "aliases": [],
                "addr": xfold(addr),
                # folded amenity surface — a dedicated recall channel that never
                # pollutes name scoring (_poi_keys stays name/alias only).
                "attrs": xfold(" ".join(attributes + tags)),
            },
        })

    pois.extend(added)

    # Category palette: keep the existing entries, add any new key the union uses.
    used = {p["category"] for p in pois}
    for k in used:
        if k not in categories and k in CATEGORIES:
            categories[k] = CATEGORIES[k]
    categories = {k: v for k, v in CATEGORIES.items() if k in used}

    _write("pois.json", {"categories": categories, "pois": pois})

    # --- Track-2 eval (semantic/ranking gold) --------------------------------
    evals = []
    for d in _sheet_dicts(wb, "Public_Evaluation"):
        evals.append({
            "query_id": _s(d["query_id"]),
            "input_query": _s(d["input_query"]),
            "query_category": _s(d["query_category"]),
            "expected_intent": _s(d["expected_intent"]),
            "expected_top_poi_ids": _semis(d["expected_top_poi_ids"]),
            "expected_top_poi_names": [t.strip() for t in _s(d["expected_top_poi_names"]).split(";") if t.strip()],
            "expected_semantic_requirements": _semis(d["expected_semantic_requirements"]),
            "ranking_signals_to_use": _semis(d["ranking_signals_to_use"]),
            "difficulty": _s(d["difficulty"]),
            "skills_tested": _s(d["skills_tested"]),
        })
    _write("eval_track2.json", {"queries": evals})

    # --- Attribute taxonomy (canonical amenity vocabulary) -------------------
    taxo = []
    for d in _sheet_dicts(wb, "Attribute_Taxonomy"):
        attr = _s(d["attribute"])
        taxo.append({
            "attribute": attr,
            "folded": fold(attr),
            "semantic_meaning": _s(d["semantic_meaning"]),
            "applicable_categories": [c.strip() for c in _s(d["applicable_categories"]).split(",") if c.strip()],
            "examples": _s(d["examples"]),
        })
    _write("attribute_taxonomy.json", {"attributes": taxo})

    enriched = sum(1 for p in pois if p["attributes"])
    print(f"counts: pois={len(pois)} (track2={len(added)}, enriched={enriched}) "
          f"eval_track2={len(evals)} taxonomy={len(taxo)}")
    print(f"cities: {sorted({p['city'] for p in pois})}")
    print(f"categories: {sorted(used)}")


if __name__ == "__main__":
    main()
