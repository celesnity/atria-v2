"""Needs + coordinate acceptance eval for tasco_jarvis_map.

Separate from the Track-1 (eval.py) and Track-2 (eval_track2.py) suites — those
stay pristine as regression guards. This measures the new needs-based-search and
coordinate-robustness guarantees:

  false_attribute_claim_rate     results claiming a need `confirmed` that the POI
                                 data does not support (ANTI-FABRICATION; target 0)
  hard_need_filter_precision     when hard needs are NOT relaxed, every result
                                 confirms them
  coordinate_parse_accuracy      coordinate queries whose lat/lng parse correctly
  coordinate_order_correction    reversed lng,lat pairs corrected
  nearby_distance_present_rate   coordinate/nearby results carrying a distance

Backend follows ATRIA_MAP_BACKEND (json | db). Run with PYTHONUTF8=1.
  python scripts/eval_needs.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import expand_abbrev, fold, load_abbreviations, load_json  # noqa: E402

import need_taxonomy  # noqa: E402
import query_intent as QI  # noqa: E402
import search as S  # noqa: E402

GATES = {
    "false_attribute_claim_rate": ("<=", 0.0),
    "hard_need_filter_precision": (">=", 0.95),
    "coordinate_parse_accuracy": (">=", 0.95),
    "coordinate_order_correction_accuracy": (">=", 0.95),
    "nearby_distance_present_rate": (">=", 1.0),
}

_CTX = QI.context()
_CATS, _POIS, _TERMS, _MX = S._load()
_IDX = S._category_index(_CATS)
_POI_BY_ID = {p["poi_id"]: p for p in _POIS}
_TR, _NG = load_abbreviations()
_NEED_IDX = need_taxonomy.build_need_index(
    lambda t: expand_abbrev(fold(t), _TR, _NG))
_SAMPLE = _POIS[0]["name"]


def _search(q: str) -> dict:
    return S.cmd_search(SimpleNamespace(
        query=q, limit=8, city=None, category=None,
        lat=None, lng=None, now=None, radius_km=None))


def _parse(q: str) -> dict:
    return QI.parse(q, _CTX, S._detect_category, _IDX)


def _confirms(poi_id: str, need_key: str) -> bool:
    """INDEPENDENT ground-truth check for anti-fabrication.

    Deliberately does NOT reuse `match_need(q.attrs)` (the search path). Instead it
    reads the POI's RAW `attributes`/`tags` via `confirms_raw` (no expand_abbrev), so
    an abbrev-expansion false positive in search would show up here as a disagreement
    (false_attribute_claim_rate > 0) rather than being tautologically confirmed."""
    p = _POI_BY_ID.get(poi_id, {})
    return need_taxonomy.confirms_raw(need_key, p.get("attributes"), p.get("tags"))


# Coordinate cases: (query, expected_lat, expected_lng, corrected, nearby)
_COORD_CASES = [
    ("10.7731,106.7039 gan day co quan cafe co wifi", 10.7731, 106.7039, False, True),
    ("106.7039,10.7731 gan day co nha thuoc nao", 10.7731, 106.7039, True, True),
    ("10.7731 106.7039 gan day co atm", 10.7731, 106.7039, False, True),
    ("lat 10.7731 lng 106.7039 co gi gan day", 10.7731, 106.7039, False, True),
    ("10.7731,106.7039 la cho nao", 10.7731, 106.7039, False, True),
    ("21.0287,105.8524 gan day co quan an", 21.0287, 105.8524, False, True),
    ("108.2208,16.0678 gan day co khach san", 16.0678, 108.2208, True, True),
]

# Needs cases run over the Track-2 public-eval queries (they carry the real
# need language). We measure claim-honesty + hard-filter precision on all of them.


def main() -> None:
    backend = os.environ.get("ATRIA_MAP_BACKEND", "json")
    print(f"=== Needs + coordinate eval (backend={backend}) ===")

    # ---- Coordinate suite ----
    parse_ok = corr_ok = corr_total = dist_ok = dist_total = 0
    for q, elat, elng, corrected, nearby in _COORD_CASES:
        p = _parse(q)
        c = p.get("coords")
        if c and abs(c[0] - elat) < 1e-4 and abs(c[1] - elng) < 1e-4:
            parse_ok += 1
        if corrected:
            corr_total += 1
            if p["entities"].get("coordinate_order_corrected") is True:
                corr_ok += 1
        if nearby:
            res = _search(q)
            rows = res.get("results") or []
            if rows:
                dist_total += 1
                if all(r.get("distance_km") is not None for r in rows):
                    dist_ok += 1

    n_coord = len(_COORD_CASES)
    coord_parse = parse_ok / n_coord
    coord_corr = (corr_ok / corr_total) if corr_total else 1.0
    dist_present = (dist_ok / dist_total) if dist_total else 1.0

    # ---- Needs suite (over Track-2 queries) ----
    cases = load_json("eval_track2.json")["queries"]
    false_claims = 0
    claim_total = 0
    hard_prec_ok = hard_prec_total = 0
    for c in cases:
        res = _search(c["input_query"])
        needs = res.get("needs") or {}
        must = needs.get("must_have") or []
        relaxed = needs.get("hard_relaxed")
        for r in res.get("results", []):
            for m in r.get("matched_needs", []):
                if m.get("source") == "attribute" and m.get("status") == "confirmed":
                    claim_total += 1
                    if not _confirms(r["poi_id"], m["need"]):
                        false_claims += 1
        if must and not relaxed:
            for r in res.get("results", []):
                hard_prec_total += 1
                mn = {m["need"]: m["status"] for m in r.get("matched_needs", [])}
                if all(mn.get(k) == "confirmed" for k in must):
                    hard_prec_ok += 1

    false_rate = (false_claims / claim_total) if claim_total else 0.0
    hard_prec = (hard_prec_ok / hard_prec_total) if hard_prec_total else 1.0

    metrics = {
        "false_attribute_claim_rate": false_rate,
        "hard_need_filter_precision": hard_prec,
        "coordinate_parse_accuracy": coord_parse,
        "coordinate_order_correction_accuracy": coord_corr,
        "nearby_distance_present_rate": dist_present,
    }
    print(f"  coordinate cases: {n_coord}  | needs cases: {len(cases)}  "
          f"| attribute claims checked: {claim_total}")
    for k, v in metrics.items():
        print(f"  {k:38} {v:.3f}")

    print("\n=== gates ===")
    all_pass = True
    for k, (op, thr) in GATES.items():
        v = metrics[k]
        ok = (v <= thr) if op == "<=" else (v >= thr)
        all_pass &= ok
        print(f"  {k:38} {v:.3f} {op} {thr}  {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
