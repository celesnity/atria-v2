"""One-off ingest: AI Maps Track-1 xlsx -> committed data/*.json.

Source workbook (kept OUTSIDE this repo):
  D:\\[Challenge]_GenaiFund\\[Project]_MapMinder\\ai_maps_track1_dataset_participants_v2.xlsx

Usage (from the repo venv, PYTHONUTF8=1):
  python scripts/ingest.py --xlsx "<path-to-xlsx>"

Outputs (committed to git — re-run only when the dataset version changes):
  data/pois.json           190 POIs + canonical category palette + folded q.* keys
  data/addresses.json      150 addresses + folded q.* keys
  data/abbreviations.json  74 folded term -> folded expansion, + max_ngram
  data/eval_queries.json   60 public-evaluation rows
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import DATA_DIR, fold  # noqa: E402

# Canonical category keys: the sheet mixes EN/VN labels for the same thing
# ("Cafe" / "Quán cà phê" / "Cafe/Tea"). Map raw PRIMARY category -> key.
RAW_TO_KEY = {
    "Cafe": "cafe", "Quán cà phê": "cafe", "Cafe/Tea": "cafe",
    "Nhà hàng": "restaurant",
    "Khách sạn": "hotel",
    "Supermarket": "supermarket",
    "Convenience Store": "convenience",
    "Shopping Mall": "mall", "Trung tâm thương mại": "mall",
    "Bank/ATM": "bank",
    "Cinema": "cinema", "Rạp chiếu phim": "cinema",
    "Hospital": "hospital", "Bệnh viện": "hospital",
    "Pharmacy": "pharmacy", "Nhà thuốc": "pharmacy",
    "Gas Station": "gas", "Cây xăng": "gas",
    "Trạm sạc điện": "ev_charging",
    "Electronics": "electronics",
    "Sân bay": "airport",
    "Bến xe": "bus_station",
    "Chợ": "market",
    "Điểm du lịch": "attraction",
}

CATEGORIES = {
    "cafe":        {"label": "Cafe",          "label_vi": "Quán cà phê",       "color": "#a5713f", "emoji": "☕"},
    "restaurant":  {"label": "Restaurant",    "label_vi": "Nhà hàng",          "color": "#e8590c", "emoji": "\U0001f35c"},
    "hotel":       {"label": "Hotel",         "label_vi": "Khách sạn",         "color": "#1971c2", "emoji": "\U0001f3e8"},
    "supermarket": {"label": "Supermarket",   "label_vi": "Siêu thị",          "color": "#2f9e44", "emoji": "\U0001f6d2"},
    "convenience": {"label": "Convenience",   "label_vi": "Cửa hàng tiện lợi", "color": "#66a80f", "emoji": "\U0001f3ea"},
    "mall":        {"label": "Mall",          "label_vi": "TT thương mại",     "color": "#9c36b5", "emoji": "\U0001f6cd"},
    "bank":        {"label": "Bank/ATM",      "label_vi": "Ngân hàng/ATM",     "color": "#0ca678", "emoji": "\U0001f3e7"},
    "cinema":      {"label": "Cinema",        "label_vi": "Rạp chiếu phim",    "color": "#6741d9", "emoji": "\U0001f3ac"},
    "hospital":    {"label": "Hospital",      "label_vi": "Bệnh viện",         "color": "#e03131", "emoji": "\U0001f3e5"},
    "pharmacy":    {"label": "Pharmacy",      "label_vi": "Nhà thuốc",         "color": "#37b24d", "emoji": "\U0001f48a"},
    "gas":         {"label": "Gas station",   "label_vi": "Cây xăng",          "color": "#f08c00", "emoji": "⛽"},
    "ev_charging": {"label": "EV charging",   "label_vi": "Trạm sạc điện",     "color": "#12b886", "emoji": "\U0001f50c"},
    "electronics": {"label": "Electronics",   "label_vi": "Điện máy",          "color": "#4263eb", "emoji": "\U0001f4f1"},
    "airport":     {"label": "Airport",       "label_vi": "Sân bay",           "color": "#3b5bdb", "emoji": "✈"},
    "bus_station": {"label": "Bus station",   "label_vi": "Bến xe",            "color": "#7a6a54", "emoji": "\U0001f68c"},
    "market":      {"label": "Market",        "label_vi": "Chợ",               "color": "#c2703e", "emoji": "\U0001f9fa"},
    "attraction":  {"label": "Attraction",    "label_vi": "Điểm du lịch",      "color": "#d6336c", "emoji": "\U0001f4f8"},
    "other":       {"label": "Other",         "label_vi": "Khác",              "color": "#868e96", "emoji": "\U0001f4cd"},
}


def _sheet_dicts(wb, name):
    rows = list(wb[name].iter_rows(values_only=True))
    hdr = [str(h).strip() for h in rows[0]]
    for r in rows[1:]:
        if r is None or all(v is None for v in r):
            continue
        yield {hdr[i]: r[i] for i in range(len(hdr))}


def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _split_aliases(raw: str, sep: str) -> list[str]:
    return [a.strip() for a in _s(raw).split(sep) if a.strip()]


def _write(name: str, payload) -> None:
    path = DATA_DIR / name
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=True, indent=1)
        fh.write("\n")
    print(f"wrote {path.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", required=True, help="path to the participants xlsx")
    args = ap.parse_args()

    import openpyxl  # repo venv dependency

    wb = openpyxl.load_workbook(args.xlsx, read_only=True)
    DATA_DIR.mkdir(exist_ok=True)

    # --- POIs -------------------------------------------------------------
    pois = []
    for d in _sheet_dicts(wb, "POI Dataset"):
        primary = _s(d["category"]).split(",")[0].strip()
        key = RAW_TO_KEY.get(primary, "other")
        aliases = _split_aliases(d["aliases"], ",")
        name_vi, name_en = _s(d["name_vi"]), _s(d["name_en"])
        try:
            rating = round(float(_s(d["rating"])), 1)
        except ValueError:
            rating = None
        pois.append({
            "poi_id": _s(d["poi_id"]),
            "name": name_vi,
            "name_en": name_en,
            "category": key,
            "category_raw": _s(d["category"]),
            "brand": _s(d["brand"]),
            "address": _s(d["address"]),
            "district": _s(d["district"]),
            "city": _s(d["city"]),
            "lat": float(d["latitude"]),
            "lng": float(d["longitude"]),
            "aliases": aliases,
            "opening_hours": _s(d["opening_hours"]),
            "rating": rating,
            "q": {
                "name": fold(name_vi),
                "name_en": fold(name_en),
                "aliases": sorted({fold(a) for a in aliases}),
                "addr": fold(f"{d['address']} {d['district']} {d['city']}"),
            },
        })
    used = {p["category"] for p in pois}
    _write("pois.json", {
        "categories": {k: v for k, v in CATEGORIES.items() if k in used},
        "pois": pois,
    })

    # --- Addresses ---------------------------------------------------------
    addresses = []
    for d in _sheet_dicts(wb, "Address Dataset"):
        aliases = _split_aliases(d["aliases"], "|")
        addresses.append({
            "address_id": _s(d["address_id"]),
            "full_address": _s(d["full_address"]),
            "house_number": _s(d["house_number"]),
            "street": _s(d["street"]),
            "ward": _s(d["ward"]),
            "district": _s(d["district"]),
            "city": _s(d["city"]),
            "lat": float(d["latitude"]),
            "lng": float(d["longitude"]),
            "aliases": aliases,
            "notes": _s(d["notes"]),
            "q": {
                "full": fold(d["full_address"]),
                "aliases": sorted({fold(a) for a in aliases}),
            },
        })
    _write("addresses.json", {"addresses": addresses})

    # --- Abbreviations -----------------------------------------------------
    terms: dict[str, str] = {}
    for d in _sheet_dicts(wb, "Abbreviation Dictionary"):
        term, norm = fold(d["term"]), fold(d["normalized_form"])
        if term and norm and term != norm:
            terms[term] = norm
    max_ngram = max(len(t.split()) for t in terms)
    _write("abbreviations.json", {"max_ngram": max_ngram, "terms": terms})

    # --- Eval queries --------------------------------------------------------
    evals = []
    for d in _sheet_dicts(wb, "Public Evaluation"):
        try:
            entities = json.loads(_s(d["expected_entities_json"]))
        except (json.JSONDecodeError, TypeError):
            entities = _s(d["expected_entities_json"])
        evals.append({
            "query_id": _s(d["query_id"]),
            "input_query": _s(d["input_query"]),
            "expected_normalized_query": _s(d["expected_normalized_query"]),
            "expected_intent": _s(d["expected_intent"]),
            "expected_entities": entities,
            "difficulty": _s(d["difficulty"]),
            "skills_tested": _s(d["skills_tested"]),
        })
    _write("eval_queries.json", {"queries": evals})

    print(f"counts: pois={len(pois)} addresses={len(addresses)} "
          f"abbreviations={len(terms)} eval={len(evals)}")


if __name__ == "__main__":
    main()
