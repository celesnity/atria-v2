"""Accuracy harness: search.py vs the 60 Public Evaluation queries.

  python scripts/eval.py [--limit N] [--verbose]

Metrics:
  poi_hit@1 / @3   queries whose expected_entities include poi_name: does a
                   fold-matching POI appear in search() top-1 / top-3?
  category_acc     queries with an expected category: does _detect_category
                   resolve to the matching canonical key?
  norm_match       fold(expected_normalized_query) == our normalize_query()
                   (informative only — ours is accent-folded by design)

Gate (plan): poi_hit@3 >= 80% on POI-name queries.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import fold, load_abbreviations, load_json, normalize_query  # noqa: E402
from search import _category_index, _detect_category, cmd_search  # noqa: E402


def _names_match(expected: str, poi: dict) -> bool:
    e = fold(expected)
    keys = [poi["q"]["name"], poi["q"]["name_en"], *poi["q"]["aliases"]]
    for k in keys:
        if not k:
            continue
        if e == k:
            return True
        shorter, longer = (k, e) if len(k) < len(e) else (e, k)
        # containment counts only for multi-token strings — a bare brand alias
        # like 'lotte' must not claim 'lotte mart go vap'
        if len(shorter.split()) >= 2 and shorter in longer:
            return True
    return False


def _expected_cat_key(expected_label: str, categories: dict, cat_idx: dict) -> str | None:
    e = fold(expected_label)
    if e in cat_idx:
        return cat_idx[e]
    for key, meta in categories.items():
        if e in (fold(meta["label"]), fold(meta["label_vi"])):
            return key
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N queries")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    queries = load_json("eval_queries.json")["queries"]
    if args.limit:
        queries = queries[: args.limit]
    pois_doc = load_json("pois.json")
    categories = pois_doc["categories"]
    poi_by_id = {p["poi_id"]: p for p in pois_doc["pois"]}
    terms, max_ngram = load_abbreviations()
    cat_idx = _category_index(categories)

    poi_total = poi_hit1 = poi_hit3 = 0
    cat_total = cat_hit = 0
    norm_total = norm_hit = 0
    failures: list[str] = []
    coverage_gaps: list[str] = []

    for q in queries:
        ents = q["expected_entities"]
        if not isinstance(ents, dict):
            continue
        res = cmd_search(SimpleNamespace(query=q["input_query"], limit=8, city=None, category=None))
        results = res["results"]

        norm_total += 1
        if fold(q["expected_normalized_query"]) == res["normalized_query"]:
            norm_hit += 1

        if "poi_name" in ents:
            # eval set references POIs beyond the participants dataset — a
            # query whose target POI simply isn't in data is a coverage gap,
            # not a search failure.
            if not any(_names_match(ents["poi_name"], p) for p in poi_by_id.values()):
                coverage_gaps.append(f"{q['query_id']} '{q['input_query']}' -> "
                                     f"'{ents['poi_name']}' not in dataset")
                continue
            poi_total += 1
            hits = [i for i, r in enumerate(results)
                    if _names_match(ents["poi_name"], poi_by_id[r["poi_id"]])]
            if hits and hits[0] == 0:
                poi_hit1 += 1
            if hits and hits[0] < 3:
                poi_hit3 += 1
            elif not hits or hits[0] >= 3:
                failures.append(f"POI  {q['query_id']} '{q['input_query']}' -> expected "
                                f"'{ents['poi_name']}', top3={[r['name'] for r in results[:3]]}")
        elif "category" in ents:
            cat_total += 1
            exp_key = _expected_cat_key(ents["category"], categories, cat_idx)
            if exp_key is None:
                cat_total -= 1  # expected category outside our taxonomy — skip
            elif res["category"] == exp_key:
                cat_hit += 1
            else:
                failures.append(f"CAT  {q['query_id']} '{q['input_query']}' -> expected "
                                f"{exp_key}, got {res['category']}")

    def pct(a: int, b: int) -> str:
        return f"{100*a/b:.0f}% ({a}/{b})" if b else "n/a"

    print(f"poi_hit@1   {pct(poi_hit1, poi_total)}")
    print(f"poi_hit@3   {pct(poi_hit3, poi_total)}")
    print(f"category    {pct(cat_hit, cat_total)}")
    print(f"norm_match  {pct(norm_hit, norm_total)}   (informative)")
    print(f"coverage_gaps: {len(coverage_gaps)} poi_name queries target POIs absent from the dataset")
    gate = poi_total == 0 or poi_hit3 / poi_total >= 0.8
    print(f"GATE (poi_hit@3 >= 80%): {'PASS' if gate else 'FAIL'}")
    if args.verbose or not gate:
        for f in failures:
            print(" ", f)
        for g in coverage_gaps:
            print("  GAP", g)
    sys.exit(0 if gate else 1)


if __name__ == "__main__":
    main()
