"""Accuracy harness: search.py vs the 60 Public Evaluation queries.

  python scripts/eval.py [--backend json|db|both] [--limit N] [--verbose]
  python scripts/eval.py --geocode [--backend ...] [--geocode-sample N]

Metrics (search pass):
  poi_hit@1 / @3   queries whose expected_entities include poi_name: does a
                   fold-matching POI appear in search() top-1 / top-3?
  category_acc     queries with an expected category: does _detect_category
                   resolve to the matching canonical key?
  norm_match       fold(expected_normalized_query) == our normalize_query()
                   (informative only — ours is accent-folded by design)
  fastpath_ok      Easy poi_name queries whose top-1 score >= 55 (the
                   jarvis_chat fast-path threshold; informative)
  latency p50/p95  wall ms per cmd_search call. On the db backend the first
                   run is COLD (one OpenAI embed per novel query); reruns hit
                   the map_query_embeddings cache.

Geocode pass (--geocode): hit@1 over a self-derived gold set (every address
queried by its q.full and each alias -> match.id must equal address_id) plus
the handwritten hard set in data/eval_geocode.json.

Gate (plan): poi_hit@3 >= 80% on POI-name queries, evaluated on the ACTIVE
backend (the one selected by ATRIA_MAP_BACKEND — what production uses).
--backend both prints json and db side by side.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _db  # noqa: E402
from _data import fold, load_json  # noqa: E402
from search import _category_index, cmd_geocode, cmd_search  # noqa: E402


# Intent-accuracy gate floor = measured json baseline (2026-07-09: 72%) minus a
# ~7-pt tolerance. The 60-query gold set has internally inconsistent intent
# labels (e.g. 'san bay tan son nhat' is tagged POI though 'san bay' is a
# category; 'atm vcb q7' is tagged Nearby though it names no proximity), so 100%
# is unreachable by design — this gate guards against routing REGRESSIONS.
INTENT_ACC_FLOOR = 0.65


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


def _pct(a: int, b: int) -> str:
    return f"{100*a/b:.0f}% ({a}/{b})" if b else "n/a"


def _lat_ms(samples: list[float], q: float) -> str:
    if not samples:
        return "n/a"
    if len(samples) == 1:
        return f"{samples[0]*1000:.0f}ms"
    return f"{statistics.quantiles(samples, n=100)[int(q*100)-1]*1000:.0f}ms"


def run_search_pass(backend: str, queries: list[dict]) -> dict:
    os.environ["ATRIA_MAP_BACKEND"] = backend
    pois_doc = load_json("pois.json")
    categories = pois_doc["categories"]
    poi_by_id = {p["poi_id"]: p for p in pois_doc["pois"]}
    cat_idx = _category_index(categories)

    m = dict(poi_total=0, poi_hit1=0, poi_hit3=0, cat_total=0, cat_hit=0,
             norm_total=0, norm_hit=0, fp_total=0, fp_hit=0, intent_total=0, intent_hit=0,
             geo_scoped=0, geo_leak=0, near_dist_total=0, near_dist_present=0)
    failures: list[str] = []
    coverage_gaps: list[str] = []
    latencies: list[float] = []

    for q in queries:
        ents = q["expected_entities"]
        if not isinstance(ents, dict):
            continue
        t0 = time.perf_counter()
        res = cmd_search(SimpleNamespace(query=q["input_query"], limit=8, city=None, category=None))
        latencies.append(time.perf_counter() - t0)
        results = res["results"]

        # Intent accuracy: the ACTUAL response intent (after any anchor revert)
        # vs the gold label.
        if q.get("expected_intent"):
            m["intent_total"] += 1
            got_intent = res.get("intent")
            if got_intent == q["expected_intent"]:
                m["intent_hit"] += 1
            else:
                failures.append(f"INT  {q['query_id']} '{q['input_query']}' -> expected "
                                f"{q['expected_intent']}, got {got_intent}")

        # Geo hygiene: a city/district-scoped answer must not span >1 city, and
        # anchored (nearby/coordinate) results must carry a distance.
        gc = res.get("geo_contract") or {}
        if gc.get("multi_city_leak_detected") is not None and (
            "city" in gc.get("hard_filters_applied", [])
            or "district" in gc.get("hard_filters_applied", [])
        ):
            m["geo_scoped"] += 1
            if gc.get("multi_city_leak_detected"):
                m["geo_leak"] += 1
                failures.append(f"LEAK {q['query_id']} '{q['input_query']}' spans multiple cities")
        if res.get("anchor"):
            for r in results:
                m["near_dist_total"] += 1
                m["near_dist_present"] += int(r.get("distance_km") is not None)

        m["norm_total"] += 1
        if fold(q["expected_normalized_query"]) == res["normalized_query"]:
            m["norm_hit"] += 1

        if "poi_name" in ents:
            # eval set references POIs beyond the participants dataset — a
            # query whose target POI simply isn't in data is a coverage gap,
            # not a search failure.
            if not any(_names_match(ents["poi_name"], p) for p in poi_by_id.values()):
                coverage_gaps.append(f"{q['query_id']} '{q['input_query']}' -> "
                                     f"'{ents['poi_name']}' not in dataset")
                continue
            m["poi_total"] += 1
            hits = [i for i, r in enumerate(results)
                    if _names_match(ents["poi_name"], poi_by_id[r["poi_id"]])]
            if hits and hits[0] == 0:
                m["poi_hit1"] += 1
            if hits and hits[0] < 3:
                m["poi_hit3"] += 1
            else:
                failures.append(f"POI  {q['query_id']} '{q['input_query']}' -> expected "
                                f"'{ents['poi_name']}', top3={[r['name'] for r in results[:3]]}")
            if q.get("difficulty") == "Easy":
                m["fp_total"] += 1
                if results and results[0].get("score", 0) >= 55:
                    m["fp_hit"] += 1
        elif "category" in ents:
            m["cat_total"] += 1
            exp_key = _expected_cat_key(ents["category"], categories, cat_idx)
            if exp_key is None:
                m["cat_total"] -= 1  # expected category outside our taxonomy — skip
            elif res["category"] == exp_key:
                m["cat_hit"] += 1
            else:
                failures.append(f"CAT  {q['query_id']} '{q['input_query']}' -> expected "
                                f"{exp_key}, got {res['category']}")

    return {"metrics": m, "failures": failures, "gaps": coverage_gaps, "latencies": latencies}


def run_geocode_pass(backend: str, sample: int) -> dict:
    os.environ["ATRIA_MAP_BACKEND"] = backend
    addresses = load_json("addresses.json")["addresses"]
    if sample:
        addresses = addresses[:sample]

    total = hit = 0
    failures: list[str] = []
    latencies: list[float] = []
    for a in addresses:
        for query in dict.fromkeys([a["q"]["full"], *a["q"]["aliases"]]):
            total += 1
            t0 = time.perf_counter()
            res = cmd_geocode(SimpleNamespace(query=query))
            latencies.append(time.perf_counter() - t0)
            match = res.get("match")
            if match and match["kind"] == "address" and match["id"] == a["address_id"]:
                hit += 1
            else:
                got = f"{match['kind']}:{match['id']}" if match else "None"
                failures.append(f"ALIAS '{query}' -> expected {a['address_id']}, got {got}")

    hand_total = hand_hit = 0
    hand = load_json("eval_geocode.json")["queries"]
    for h in hand:
        hand_total += 1
        t0 = time.perf_counter()
        res = cmd_geocode(SimpleNamespace(query=h["query"]))
        latencies.append(time.perf_counter() - t0)
        match = res.get("match")
        if match and match["kind"] == h["expected_kind"] and match["id"] == h["expected_id"]:
            hand_hit += 1
        else:
            got = f"{match['kind']}:{match['id']}" if match else "None"
            failures.append(f"HAND {h['id']} '{h['query']}' -> expected "
                            f"{h['expected_kind']}:{h['expected_id']}, got {got}")

    return {"total": total, "hit": hit, "hand_total": hand_total, "hand_hit": hand_hit,
            "failures": failures, "latencies": latencies}


def run_city_pass(backend: str, queries: list[dict]) -> dict:
    """City precision: every query names a city (any alias form derived by the
    gazetteer); PASS iff results are non-empty AND all top-5 lie in that city.
    0 results counts as a failure (coverage of each city x category pair was
    verified when the gold set was authored)."""
    os.environ["ATRIA_MAP_BACKEND"] = backend
    total = hit = 0
    failures: list[str] = []
    for q in queries:
        total += 1
        res = cmd_search(SimpleNamespace(query=q["query"], limit=5, city=None, category=None))
        results = res.get("results", [])
        ok = bool(results) and all(q["expected_city"] in fold(r["city"]) for r in results)
        if ok:
            hit += 1
        else:
            got = sorted({fold(r["city"]) for r in results}) or ["0 results"]
            failures.append(f"CITY {q['id']} '{q['query']}' -> expected "
                            f"{q['expected_city']}, got {got} (detected city={res.get('city')})")
    return {"total": total, "hit": hit, "failures": failures}


def run_anchored_pass(backend: str, queries: list[dict]) -> dict:
    """Anchored / coordinate / navigation retrieval against a gold set. A query
    PASSES when intent + category + anchor kind match the gold and the result
    count / category purity hold (min_results 0 = a disclosed coverage gap)."""
    os.environ["ATRIA_MAP_BACKEND"] = backend
    total = hit = 0
    failures: list[str] = []
    for q in queries:
        total += 1
        res = cmd_search(SimpleNamespace(query=q["query"], limit=8, city=None, category=None))
        results = res.get("results", [])
        anchor = res.get("anchor")
        got_kind = anchor.get("kind") if anchor else None
        reasons = []
        if res.get("intent") != q["intent"]:
            reasons.append(f"intent={res.get('intent')}")
        if q.get("category") is not None and res.get("category") != q["category"]:
            reasons.append(f"category={res.get('category')}")
        if got_kind != q["anchor_kind"]:
            reasons.append(f"anchor_kind={got_kind}")
        if len(results) < q["min_results"]:
            reasons.append(f"n={len(results)}<{q['min_results']}")
        if q.get("all_category") and q.get("category"):
            bad = sorted({r["category"] for r in results if r["category"] != q["category"]})
            if bad:
                reasons.append(f"off_category={bad}")
        if reasons:
            failures.append(f"ANCH {q['id']} '{q['query']}' -> " + ", ".join(reasons))
        else:
            hit += 1
    return {"total": total, "hit": hit, "failures": failures}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["json", "db", "both"], default=None,
                    help="engine(s) to evaluate (default: active ATRIA_MAP_BACKEND)")
    ap.add_argument("--limit", type=int, default=0, help="only first N queries")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--geocode", action="store_true", help="run the geocode accuracy pass")
    ap.add_argument("--geocode-sample", type=int, default=0,
                    help="limit geocode gold set to first N addresses (0 = all 150)")
    args = ap.parse_args()

    active = _db.backend()
    choice = args.backend or active
    backends = ["json", "db"] if choice == "both" else [choice]
    gate_backend = active if choice == "both" else choice
    env_before = os.environ.get("ATRIA_MAP_BACKEND")

    # Observability: a db backend that can't reach the container silently falls
    # back to JSON — which would make these numbers a lie. Surface the real engine
    # health up front so `--backend db` can never quietly degrade unnoticed.
    if "db" in backends:
        import map_doctor
        os.environ["ATRIA_MAP_BACKEND"] = "db"
        _health = map_doctor.diagnose()
        os.environ["ATRIA_MAP_BACKEND"] = env_before or active
        print(f"ENGINE[db]: {'OK' if _health['ok'] else 'FALLBACK/UNHEALTHY'} "
              f"-- {_health['verdict']}")

    try:
        if args.geocode:
            passes = {b: run_geocode_pass(b, args.geocode_sample) for b in backends}
            rows = [
                ("geocode_hit@1 (alias set)", lambda r: _pct(r["hit"], r["total"])),
                ("geocode_hit@1 (handwritten)", lambda r: _pct(r["hand_hit"], r["hand_total"])),
                ("latency p50", lambda r: _lat_ms(r["latencies"], 0.50)),
                ("latency p95", lambda r: _lat_ms(r["latencies"], 0.95)),
            ]
            header = f"{'metric':<30}" + "".join(f"{b:<16}" for b in backends)
            print(header)
            for label, fn in rows:
                print(f"{label:<30}" + "".join(f"{fn(passes[b]):<16}" for b in backends))
            if args.verbose:
                for b in backends:
                    for f in passes[b]["failures"][:25]:
                        print(f"  [{b}]", f)
            return

        queries = load_json("eval_queries.json")["queries"]
        if args.limit:
            queries = queries[: args.limit]

        passes = {b: run_search_pass(b, queries) for b in backends}
        city_queries = load_json("eval_city.json")["queries"]
        city_passes = {b: run_city_pass(b, city_queries) for b in backends}
        anchored_queries = load_json("eval_anchored.json")["queries"]
        anchored_passes = {b: run_anchored_pass(b, anchored_queries) for b in backends}

        rows = [
            ("poi_hit@1", lambda m: _pct(m["poi_hit1"], m["poi_total"])),
            ("poi_hit@3", lambda m: _pct(m["poi_hit3"], m["poi_total"])),
            ("category", lambda m: _pct(m["cat_hit"], m["cat_total"])),
            ("intent_acc", lambda m: _pct(m["intent_hit"], m["intent_total"])),
            ("norm_match (informative)", lambda m: _pct(m["norm_hit"], m["norm_total"])),
            ("fastpath>=55 (informative)", lambda m: _pct(m["fp_hit"], m["fp_total"])),
            ("city_leak_rate (want 0%)", lambda m: _pct(m["geo_leak"], m["geo_scoped"])),
            ("nearby_dist_present", lambda m: _pct(m["near_dist_present"], m["near_dist_total"])),
        ]
        header = f"{'metric':<30}" + "".join(f"{b:<16}" for b in backends)
        print(header)
        for label, fn in rows:
            print(f"{label:<30}" + "".join(f"{fn(passes[b]['metrics']):<16}" for b in backends))
        print(f"{'city_precision':<30}"
              + "".join(f"{_pct(city_passes[b]['hit'], city_passes[b]['total']):<16}"
                        for b in backends))
        print(f"{'anchored_pass':<30}"
              + "".join(f"{_pct(anchored_passes[b]['hit'], anchored_passes[b]['total']):<16}"
                        for b in backends))
        for label, q in [("latency p50", 0.50), ("latency p95", 0.95)]:
            print(f"{label:<30}" + "".join(f"{_lat_ms(passes[b]['latencies'], q):<16}" for b in backends))
        gaps = passes[backends[0]]["gaps"]
        print(f"coverage_gaps: {len(gaps)} poi_name queries target POIs absent from the dataset")
        if "db" in backends:
            print("(db latency: first run is cold — one OpenAI embed per novel query; "
                  "reruns hit the query-embedding cache)")

        gm = passes[gate_backend]["metrics"]
        gate = gm["poi_total"] == 0 or gm["poi_hit3"] / gm["poi_total"] >= 0.8
        print(f"GATE (poi_hit@3 >= 80% on '{gate_backend}'): {'PASS' if gate else 'FAIL'}")
        cm = city_passes[gate_backend]
        city_gate = cm["total"] == 0 or cm["hit"] / cm["total"] >= 0.95
        print(f"GATE (city_precision >= 95% on '{gate_backend}'): "
              f"{'PASS' if city_gate else 'FAIL'}")
        # Intent gate = measured-baseline minus a 5-pt tolerance (labels in the
        # gold set are themselves inconsistent — e.g. 'atm vcb q7' is tagged
        # Nearby though it names no proximity — so 100% is neither reachable nor
        # the goal; the gate guards against a REGRESSION in routing).
        im = gm["intent_hit"] / gm["intent_total"] if gm["intent_total"] else 1.0
        intent_gate = im >= INTENT_ACC_FLOOR
        print(f"GATE (intent_acc >= {INTENT_ACC_FLOOR:.0%} on '{gate_backend}'): "
              f"{'PASS' if intent_gate else 'FAIL'}")
        am = anchored_passes[gate_backend]
        anchored_gate = am["total"] == 0 or am["hit"] / am["total"] >= 0.8
        print(f"GATE (anchored_pass >= 80% on '{gate_backend}'): "
              f"{'PASS' if anchored_gate else 'FAIL'}")
        all_gates = gate and city_gate and intent_gate and anchored_gate
        if args.verbose or not all_gates:
            for b in backends:
                for f in (passes[b]["failures"] + city_passes[b]["failures"]
                          + anchored_passes[b]["failures"]):
                    print(f"  [{b}]", f)
            for g in gaps:
                print("  GAP", g)
        sys.exit(0 if all_gates else 1)
    finally:
        if env_before is None:
            os.environ.pop("ATRIA_MAP_BACKEND", None)
        else:
            os.environ["ATRIA_MAP_BACKEND"] = env_before


if __name__ == "__main__":
    main()
