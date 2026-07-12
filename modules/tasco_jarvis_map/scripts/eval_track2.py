"""Track-2 semantic/ranking self-eval against data/eval_track2.json.

For each of the 60 Track-2 Public_Evaluation queries this runs the deterministic
router (cmd_search, the same engine the agent fast-path calls) and scores:

  poi_hit@3     any expected_top_poi_id in the top 3 results
  recall@3/@5   fraction of expected ids retrieved in the top 3 / 5
  intent_acc    competition intent == expected_intent
  reason_cov    fraction of expected_semantic_requirements reflected in the
                matched amenities/attributes of the top 3 results (explainability)

Backend follows ATRIA_MAP_BACKEND (json | db). Run with PYTHONUTF8=1.
  python scripts/eval_track2.py            # summary + gates
  python scripts/eval_track2.py --show 8   # + per-case detail for the first 8
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _data import fold, load_json  # noqa: E402

import search  # noqa: E402

# Gates are asserted on the DB (vector) engine — Track-2 is a *semantic* benchmark
# and its implicit-category queries ("rooftop", "resort", "phở") only retrieve with
# embeddings; the JSON engine is the degraded no-embeddings fallback.
#   poi_hit@3  0.80  — an expected POI in the top 3 (db earns 0.817).
#   reason_cov 0.35  — set BELOW the measured data-present ceiling (~0.50: only half
#                      the expected requirements are literal amenities of a retrieved
#                      POI; the rest are geo/concept needs like "gần trung tâm" or
#                      concept-expansion like work->wifi that no data field carries).
#                      The raw reason_cov and that ceiling are both printed so the
#                      real number is visible next to the gate.
# intent_acc is INFORMATIVE, not a gate: our router uses the finer-grained Track-1
# competition taxonomy (9 archetypes) — it routes "cafe gần hồ gươm" as Nearby to
# fire distance ranking, where Track-2's 6-label scheme folds it into Category
# Search. The divergence is definitional; forcing the label would regress the
# Track-1 anchored_pass gate. Retrieval quality is measured by poi_hit@3/recall.
GATES = {"poi_hit@3": 0.80, "reason_cov": 0.35}


def _covered(req: str, attrs: list[str]) -> bool:
    """Is an expected semantic requirement satisfied by a POI's amenity phrases?
    Token-subset match on the folded forms ("wifi" ~ "wi-fi" via fold-insensitive
    containment; "làm việc" ~ "phù hợp làm việc")."""
    rt = set(fold(req).replace("-", " ").split())
    if not rt:
        return False
    for a in attrs:
        at = set(fold(a).replace("-", " ").split())
        if rt <= at or rt & at == rt:
            return True
    # last resort: token overlap >= half the requirement tokens
    for a in attrs:
        at = set(fold(a).replace("-", " ").split())
        if len(rt & at) >= max(1, len(rt) // 2) and (rt & at):
            return True
    return False


def _run(query: str, limit: int = 5) -> dict:
    return search.cmd_search(SimpleNamespace(
        query=query, limit=limit, city=None, category=None, prior=None))


def main() -> None:
    # This eval is the only one that prints raw Vietnamese (weak-case input_query),
    # so a cp1252 Windows console would raise UnicodeEncodeError. Force UTF-8 stdout
    # (errors='replace') so it never crashes regardless of PYTHONUTF8/codepage.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show", type=int, default=0, help="print detail for first N cases")
    args = ap.parse_args()

    # This eval's gates are calibrated on the db (vector) engine; surface the real
    # engine health so a silent JSON fallback (stopped container / missing driver)
    # is obvious instead of quietly scoring the wrong engine.
    import map_doctor
    _health = map_doctor.diagnose()
    print(f"ENGINE: {_health['backend']} "
          f"({'OK' if _health['ok'] else 'FALLBACK/UNHEALTHY'}) -- {_health['verdict']}")

    cases = load_json("eval_track2.json")["queries"]
    n = len(cases)
    # POI attribute index — for the reason CEILING (how many expected requirements
    # a retrieved POI could satisfy from its own data, regardless of surfacing).
    pois = {p["poi_id"]: p for p in load_json("pois.json")["pois"]}
    hit3 = rec3 = rec5 = intent_ok = reason_cov = reason_ceiling = 0.0
    misses = []

    for i, c in enumerate(cases):
        res = _run(c["input_query"])
        results = res.get("results", [])
        ids = [r["poi_id"] for r in results]
        exp = set(c["expected_top_poi_ids"])
        top3, top5 = set(ids[:3]), set(ids[:5])
        h3 = bool(exp & top3)
        r3 = len(exp & top3) / len(exp) if exp else 0.0
        r5 = len(exp & top5) / len(exp) if exp else 0.0
        hit3 += h3
        rec3 += r3
        rec5 += r5
        i_ok = fold(res.get("intent", "")) == fold(c["expected_intent"])
        intent_ok += i_ok
        # explainability: union of surfaced reasons vs. the attributes a retrieved
        # POI actually HOLDS (the ceiling) across the top-3 results.
        top_attrs: list[str] = []
        top_data: list[str] = []
        for r in results[:3]:
            top_attrs += r.get("reasons", [])
            p = pois.get(r["poi_id"], {})
            top_data += (p.get("attributes") or []) + (p.get("tags") or [])
        reqs = c["expected_semantic_requirements"]
        cov = (sum(_covered(rq, top_attrs) for rq in reqs) / len(reqs)) if reqs else 1.0
        ceil = (sum(_covered(rq, top_data) for rq in reqs) / len(reqs)) if reqs else 1.0
        reason_cov += cov
        reason_ceiling += ceil
        if not h3 or cov < 0.5:
            misses.append((c["query_id"], c["input_query"], list(exp), ids[:3],
                           round(cov, 2), c["difficulty"]))
        if args.show and i < args.show:
            print(f"\n[{c['query_id']}] {c['input_query']}  (diff={c['difficulty']})")
            print(f"   intent {res.get('intent')} (exp {c['expected_intent']}) "
                  f"{'OK' if i_ok else 'X'}")
            print(f"   want {sorted(exp)}  got {ids[:5]}  hit3={h3} r3={r3:.2f}")
            print(f"   reqs {reqs} -> cov {cov:.2f}; top-attrs {top_attrs[:6]}")

    # Authoritative backend: _db.backend() consults the process env AND the repo
    # .env (where ATRIA_MAP_BACKEND=db lives), so a plain `python eval_track2.py`
    # is correctly reported as 'db' — os.environ alone would mislabel it 'json'.
    backend = _health["backend"]
    print(f"\n=== Track-2 semantic eval (backend={backend}, n={n}) ===")
    metrics = {
        "poi_hit@3": hit3 / n,
        "recall@3": rec3 / n,
        "recall@5": rec5 / n,
        "intent_acc": intent_ok / n,
        "reason_cov": reason_cov / n,
    }
    for k, v in metrics.items():
        tag = "  (informative — taxonomy divergence, see GATES)" if k == "intent_acc" else ""
        print(f"  {k:12} {v:.3f}{tag}")
    ceil = reason_ceiling / n
    surfaced = (reason_cov / reason_ceiling) if reason_ceiling else 0.0
    print(f"  {'reason_ceil':12} {ceil:.3f}  (informative — max reason_cov from POI data; "
          f"surfacing {surfaced:.0%} of it)")

    if backend != "db":
        print("  NOTE: gates assert on backend=db (vector engine); this run is "
              f"'{backend}'.")

    print("\n=== gates ===")
    all_pass = True
    for k, floor in GATES.items():
        ok = metrics[k] >= floor
        all_pass &= ok
        print(f"  {k:12} {metrics[k]:.3f} >= {floor:.2f}  {'PASS' if ok else 'FAIL'}")

    if misses:
        print(f"\n=== {len(misses)} weak cases (miss@3 or low reason-cov) ===")
        for qid, q, exp, got, cov, diff in misses[:25]:
            print(f"  {qid} [{diff}] {q}\n     want {exp} got {got} cov={cov}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
