"""Agent-level + deterministic bench for the 60 Public Evaluation cases.

Produces an Agent-Level Bench Report (bench/REPORT_TEMPLATE.md format) for the
tasco_jarvis_map query-understanding work, measured against the dataset's
"Public Evaluation" sheet (mirrored in data/eval_queries.json, PUB001..PUB060).

Two levels, like the reference template:
  1. Deterministic baseline  - reuses eval.py (intent_acc, poi_hit, category,
     norm_match, city_precision, anchored_pass, latency) on json + db backends.
  2. Agent-level pass         - drives the REAL Jarvis pipeline per case
     (scripts/jarvis_chat.py -> POST /api/modules/tasco_jarvis_map/chat, app
     model), collects behaviour signals, and asks a separate LLM judge
     (gpt-5-mini) whether the answer + map actions satisfy the query. Compound
     gate PASS = places_used AND intent_ok AND judge.behavior_ok.

Usage:
  python scripts/pub_bench.py [--limit N] [--backend json|db|both]
                              [--no-agent] [--agent-backend json|db]
                              [--judge-model gpt-5-mini] [--out DIR]

Prereqs: backend running (ATRIA_API_BASE), OPENAI_API_KEY set, DB healthy.
Discipline: MEASURE-ONLY. Nothing here tunes the router or prompts.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent
MODULE = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import _db  # noqa: E402
import eval as evalh  # noqa: E402  (module eval.py; reused deterministic passes)
from _data import fold, load_json  # noqa: E402
from _sample import stratified_sample  # noqa: E402
from search import cmd_search  # noqa: E402

BENCH_USER_ID = os.environ.get("BENCH_USER_ID", "1")
API_BASE = os.environ.get("ATRIA_API_BASE", "http://127.0.0.1:8080")
DEFAULT_JUDGE = "gpt-5-mini"
AGENT_TIMEOUT_S = 150
TEMPLATE = MODULE / "bench" / "REPORT_TEMPLATE.md"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "n/a"


def _lat_ms(samples: list[float], q: float) -> str:
    if not samples:
        return "n/a"
    if len(samples) == 1:
        return f"{samples[0] * 1000:.0f}ms"
    return f"{statistics.quantiles(samples, n=100)[int(q * 100) - 1] * 1000:.0f}ms"


def city_centroids(pois: list[dict]) -> tuple[dict, tuple[float, float]]:
    """Mean lat/lng per city (folded name) + a default. Data-derived so the
    viewport hint scales to any city with zero hardcoded coordinates. The default
    is the DENSEST city's centroid (most POIs) - a real populated point - NOT the
    global mean, which for far-apart cities lands in empty space and would make
    every 'near me' case return nothing."""
    agg: dict = defaultdict(lambda: [0.0, 0.0, 0])
    for p in pois:
        c = fold(p.get("city") or "")
        agg[c][0] += p["lat"]; agg[c][1] += p["lng"]; agg[c][2] += 1
    cent = {c: (v[0] / v[2], v[1] / v[2]) for c, v in agg.items() if v[2]}
    densest = max(agg.values(), key=lambda v: v[2])
    default = (densest[0] / densest[2], densest[1] / densest[2])
    return cent, default


def pick_viewport(case: dict, cent: dict, glob: tuple) -> dict:
    """City-center viewport so 'near me' / current_location cases are exercisable.
    Matches an explicit city mention in the gold; else the global centroid."""
    hay = fold(case.get("expected_normalized_query", "") + " "
               + json.dumps(case.get("expected_entities", {}), ensure_ascii=False))
    best = None
    for cfold, latlng in cent.items():
        if cfold and cfold in hay:
            if best is None or len(cfold) > len(best[0]):
                best = (cfold, latlng)
    lat, lng = best[1] if best else glob
    return {"lat": lat, "lng": lng, "zoom": 14}


def expected_names(ents: dict) -> list[str]:
    if not isinstance(ents, dict):
        return []
    if ents.get("poi_name"):
        return [ents["poi_name"]]
    if ents.get("candidates"):
        return [c for c in ents["candidates"] if c]
    return []


# ---------------------------------------------------------------------------
# agent driver (real Jarvis loopback)
# ---------------------------------------------------------------------------
def run_agent(case: dict, viewport: dict) -> dict:
    env = {**os.environ,
           "ATRIA_API_BASE": API_BASE,
           "ATRIA_USER_ID": str(BENCH_USER_ID),
           "ATRIA_SESSION_ID": "default",
           "PYTHONUTF8": "1"}
    payload = {"message": case["input_query"],
               "chat_session_id": f"bench-{case['query_id']}",
               "viewport": viewport}
    try:
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / "jarvis_chat.py")],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True, env=env, timeout=AGENT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"reply": "", "map_actions": [], "source": "agent",
                "error": f"timeout>{AGENT_TIMEOUT_S}s"}
    try:
        out = json.loads(p.stdout.decode("utf-8") or "{}")
    except ValueError:
        return {"reply": "", "map_actions": [], "source": "agent",
                "error": f"bad agent stdout: {p.stderr.decode('utf-8', 'replace')[:160]}"}
    out.setdefault("map_actions", [])
    out.setdefault("source", "agent")
    return out


# ---------------------------------------------------------------------------
# judge (separate LLM; strict JSON verdict)
# ---------------------------------------------------------------------------
JUDGE_SYS = (
    "You are a strict evaluator for a Vietnamese maps search assistant. Given a "
    "user query, the GOLD understanding (expected intent, normalized query, "
    "entities), the resolved reference point, and the assistant's ANSWER plus the "
    "PINNED places, decide if the assistant correctly satisfied the query. Judge "
    "behaviour/answer correctness, not exact wording; Vietnamese and English are "
    "both fine. "
    "PROXIMITY applies ONLY to Nearby/Coordinate intents or when a reference_point "
    "is given. For those, each pinned place lists its ACTUAL distance ('dist_km'); "
    "judge 'near' ONLY from these numbers - do NOT infer distance from street or "
    "district names (they are unreliable). reference_point may be null for 'near "
    "me' queries - then dist_km is measured from the user's current map location. "
    "A place within a few km counts as near; ranked-by-distance results are correct "
    "even if the nearest available venue is a couple km away in this sparse "
    "synthetic dataset. For POI/Category/Brand/Discovery searches, distance is "
    "IRRELEVANT - judge only whether the pinned places match the requested "
    "category/brand/name/city; never penalise missing dist_km for these. "
    "Navigation: must give directions/route to the correct destination. "
    "POI/Category/Nearby/Brand/Discovery: must surface relevant place(s) matching "
    "the category/brand/location; naming suitable venues counts as correct. "
    "Ambiguous: must disambiguate (ask which) or present the candidate set. "
    "Coordinate: must return places near the coordinate. If the requested place "
    "is NOT in the dataset, a graceful 'not found / here are alternatives' is "
    "CORRECT, but fabricating a specific place/address/opening-hours is INCORRECT. "
    'Return STRICT JSON only: {"behavior_ok": true|false, "reason": "<=200 chars, one sentence"}.'
)


def make_judge(model: str, votes: int = 3):
    """Majority-vote judge: gpt-5 disallows temperature=0, so a single verdict is
    noisy; run `votes` calls (different seeds) and take the majority behavior_ok.
    Ties (only possible when some calls error) resolve conservatively to False."""
    from openai import OpenAI

    client = OpenAI(api_key=_db.env_get("OPENAI_API_KEY"))

    def _one(user: str, seed: int) -> tuple:
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": JUDGE_SYS},
                          {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                seed=seed,
                max_completion_tokens=6000)
            if r.choices[0].finish_reason == "length":
                return (None, "judge truncated", True)
            v = json.loads(r.choices[0].message.content)
            return (bool(v.get("behavior_ok")), str(v.get("reason", ""))[:200], False)
        except Exception as exc:  # a judge call must never crash the run
            return (None, f"judge error: {exc}"[:200], True)

    def judge(case: dict, agent: dict, router: dict) -> dict:
        actions = agent.get("map_actions", [])
        # Distance-aware pin list: the agent's pin `detail` starts with "<km> km ..."
        # for anchored/coordinate/nearby results (distance the USER actually saw -
        # relative to the resolved anchor, or to the viewport for 'near me'). Parse
        # it directly so the judge sees real proximity instead of guessing.
        pins = []
        for a in actions:
            if a.get("type") != "pins":
                continue
            for it in a.get("items", []):
                d = it.get("detail") or ""
                mm = re.match(r"^\s*([\d.]+)\s*km", d)
                pins.append({"name": it.get("name"),
                             "dist_km": float(mm.group(1)) if mm else None,
                             "detail": d})
        anchor = router.get("anchor")
        user = json.dumps({
            "query": case["input_query"],
            "expected_intent": case.get("expected_intent"),
            "expected_normalized_query": case.get("expected_normalized_query"),
            "expected_entities": case.get("expected_entities"),
            "reference_point": ({"label": anchor.get("label"), "kind": anchor.get("kind"),
                                 "resolution": anchor.get("resolution")} if anchor else None),
            "assistant_answer": agent.get("reply", ""),
            "map_action_types": [a.get("type") for a in actions],
            "pinned_places": pins[:12],
        }, ensure_ascii=False)

        results = [_one(user, seed=7 + i) for i in range(votes)]
        valid = [(ok, rs) for ok, rs, err in results if not err]
        if not valid:
            return {"behavior_ok": None, "reason": results[0][1], "judge_error": True,
                    "judge_votes": "0 valid"}
        true_n = sum(1 for ok, _ in valid if ok)
        majority = (true_n * 2) > len(valid)  # strict majority; tie -> False
        reason = next((rs for ok, rs in valid if ok == majority), valid[0][1])
        return {"behavior_ok": majority, "reason": reason, "judge_error": False,
                "judge_votes": f"{true_n}/{len(valid)} true"}

    return judge


# ---------------------------------------------------------------------------
# per-case scoring
# ---------------------------------------------------------------------------
def map_action_ok(expected_intent: str, actions: list[dict], had_results: bool) -> bool:
    types = {a.get("type") for a in actions}
    if expected_intent == "Navigation":
        return "route" in types or "pins" in types
    if expected_intent == "Coordinate Search":
        return "pins" in types or "focus" in types
    if expected_intent == "Ambiguous":
        return True  # pins (candidate set) or a clarifying reply both acceptable
    return ("pins" in types) or (not had_results)  # nothing to pin if 0 results


def score_case(case: dict, viewport: dict, judge) -> dict:
    ents = case.get("expected_entities") or {}
    # Router signals (deterministic; active backend = production).
    router = cmd_search(SimpleNamespace(query=case["input_query"], limit=8, city=None, category=None))
    got_intent = router.get("intent")
    results = router.get("results") or []
    intent_ok = got_intent == case.get("expected_intent")

    # Agent behaviour (real pipeline).
    t0 = time.perf_counter()
    agent = run_agent(case, viewport)
    wall = time.perf_counter() - t0
    actions = agent.get("map_actions", [])
    pin_names = [it.get("name", "") for a in actions if a.get("type") == "pins"
                 for it in a.get("items", [])]
    run_error = bool(agent.get("error")) or not (agent.get("reply") or "").strip()

    places_used = bool(results) or any(a.get("type") == "pins" for a in actions)
    mao = map_action_ok(case.get("expected_intent"), actions, bool(results))

    names = expected_names(ents)
    recall_hits = 0
    if names:
        blob = fold(agent.get("reply", "") + " " + " ".join(pin_names))
        recall_hits = sum(1 for n in names if fold(n) in blob)
    name_recall = (recall_hits, len(names))

    verdict = {"behavior_ok": None, "reason": "", "judge_error": False}
    if not run_error and judge is not None:
        verdict = judge(case, agent, router)

    behavior_ok = verdict.get("behavior_ok")
    compound_pass = bool(places_used and intent_ok and behavior_ok)

    return {
        "query_id": case["query_id"],
        "input_query": case["input_query"],
        "difficulty": case.get("difficulty"),
        "expected_intent": case.get("expected_intent"),
        "got_intent": got_intent,
        "intent_ok": intent_ok,
        "places_used": places_used,
        "source": agent.get("source"),
        "map_action_ok": mao,
        "name_recall": name_recall,
        "run_error": run_error,
        "behavior_ok": behavior_ok,
        "judge_error": verdict.get("judge_error", False),
        "judge_votes": verdict.get("judge_votes"),
        "judge_reason": verdict.get("reason", ""),
        "compound_pass": compound_pass,
        "confidence_score": router.get("confidence_score"),
        "reply": agent.get("reply", ""),
        "action_types": [a.get("type") for a in actions],
        "pinned": pin_names[:8],
        "wall_s": round(wall, 1),
        "agent_error": agent.get("error"),
    }


# ---------------------------------------------------------------------------
# deterministic baseline (reuse eval.py)
# ---------------------------------------------------------------------------
def deterministic_baseline(queries: list[dict], backends: list[str]) -> dict:
    env_before = os.environ.get("ATRIA_MAP_BACKEND")
    try:
        search_pass = {b: evalh.run_search_pass(b, queries) for b in backends}
        city_q = load_json("eval_city.json")["queries"]
        city_pass = {b: evalh.run_city_pass(b, city_q) for b in backends}
        anch_q = load_json("eval_anchored.json")["queries"]
        anch_pass = {b: evalh.run_anchored_pass(b, anch_q) for b in backends}
    finally:
        if env_before is None:
            os.environ.pop("ATRIA_MAP_BACKEND", None)
        else:
            os.environ["ATRIA_MAP_BACKEND"] = env_before
    return {"search": search_pass, "city": city_pass, "anchored": anch_pass}


# ---------------------------------------------------------------------------
# report rendering
# ---------------------------------------------------------------------------
def _grouped_rate(records: list[dict], key: str, ok_field: str) -> str:
    buckets: dict = defaultdict(lambda: [0, 0])
    for r in records:
        b = buckets[r.get(key)]
        b[1] += 1
        if r.get(ok_field):
            b[0] += 1
    lines = [f"- {k}: {pct(v[0], v[1])}" for k, v in sorted(buckets.items(), key=lambda x: str(x[0]))]
    return "\n".join(lines)


def render_report(records: list[dict], baseline: dict, backends: list[str],
                  gate_backend: str, agent_model: str, judge_model: str,
                  temp_note: str, total_cases: int,
                  sample_meta: dict | None = None) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")

    # A stratified subset ran (fast quick check) — annotate the report so the
    # numbers aren't mistaken for the full run. Empty on a full/on-demand run,
    # which keeps the full report structurally identical to before.
    if sample_meta:
        pl = sample_meta["per_level"]
        ids = ", ".join(sample_meta["picked_ids"])
        sample_note = (
            f"\n\n**Sample: {len(records)} of {sample_meta['n_full']} cases** — "
            f"stratified {int(sample_meta['fraction'] * 100)}% by "
            f"{sample_meta['level_key']} ({', '.join(f'{k} {pl[k]}' for k in pl)}), "
            f"seed {sample_meta['seed']} (reproduce with `--seed {sample_meta['seed']}`; "
            f"`--full` runs all {sample_meta['n_full']}). "
            f"A random subset is a fast smoke check, not a regression sign-off. "
            f"Cases: {ids}."
        )
    else:
        sample_note = ""

    # --- baseline aggregate (gate backend) ---
    m = baseline["search"][gate_backend]["metrics"]
    cityp = baseline["city"][gate_backend]
    anchp = baseline["anchored"][gate_backend]

    def two_backend(fn) -> str:
        return " | ".join(f"{b}: {fn(b)}" for b in backends)

    intent_acc = two_backend(lambda b: pct(baseline["search"][b]["metrics"]["intent_hit"],
                                            baseline["search"][b]["metrics"]["intent_total"]))
    poi1 = two_backend(lambda b: pct(baseline["search"][b]["metrics"]["poi_hit1"],
                                     baseline["search"][b]["metrics"]["poi_total"]))
    poi3 = two_backend(lambda b: pct(baseline["search"][b]["metrics"]["poi_hit3"],
                                     baseline["search"][b]["metrics"]["poi_total"]))
    cat = two_backend(lambda b: pct(baseline["search"][b]["metrics"]["cat_hit"],
                                    baseline["search"][b]["metrics"]["cat_total"]))
    norm = two_backend(lambda b: pct(baseline["search"][b]["metrics"]["norm_hit"],
                                     baseline["search"][b]["metrics"]["norm_total"]))
    cityprec = two_backend(lambda b: pct(baseline["city"][b]["hit"], baseline["city"][b]["total"]))
    anch = two_backend(lambda b: pct(baseline["anchored"][b]["hit"], baseline["anchored"][b]["total"]))

    gate = m["poi_total"] == 0 or m["poi_hit3"] / m["poi_total"] >= 0.8
    im = m["intent_hit"] / m["intent_total"] if m["intent_total"] else 1.0
    cg = cityp["total"] == 0 or cityp["hit"] / cityp["total"] >= 0.95
    ag = anchp["total"] == 0 or anchp["hit"] / anchp["total"] >= 0.8
    gates = (f"poi_hit@3>=80% {'PASS' if gate else 'FAIL'}, "
             f"intent_acc>=65% {'PASS' if im >= 0.65 else 'FAIL'} ({im:.0%}), "
             f"city_precision>=95% {'PASS' if cg else 'FAIL'}, "
             f"anchored_pass>=80% {'PASS' if ag else 'FAIL'} (gate backend: {gate_backend})")

    # baseline intent grouping (own per-case router intent from records)
    intent_by_intent = _grouped_rate(records, "expected_intent", "intent_ok")
    intent_by_diff = _grouped_rate(records, "difficulty", "intent_ok")

    # --- agent-level aggregate ---
    n = len(records)
    passed = sum(1 for r in records if r["compound_pass"])
    behavior = sum(1 for r in records if r["behavior_ok"])
    places = sum(1 for r in records if r["places_used"])
    mao = sum(1 for r in records if r["map_action_ok"])
    run_err = sum(1 for r in records if r["run_error"])
    judge_err = sum(1 for r in records if r["judge_error"])
    fast = sum(1 for r in records if r["source"] == "fast")
    agentp = sum(1 for r in records if r["source"] == "agent")

    rec_cases = [r for r in records if r["name_recall"][1] > 0]
    rec_any = sum(1 for r in rec_cases if r["name_recall"][0] > 0)
    rec_ind_hit = sum(r["name_recall"][0] for r in rec_cases)
    rec_ind_tot = sum(r["name_recall"][1] for r in rec_cases)

    pass_by_intent = _grouped_rate(records, "expected_intent", "compound_pass")
    pass_by_diff = _grouped_rate(records, "difficulty", "compound_pass")

    fails = []
    for r in sorted(records, key=lambda x: x["query_id"]):
        if r["compound_pass"]:
            continue
        if r["run_error"]:
            tag = "run-error"
        elif r["behavior_ok"] and not r["intent_ok"]:
            tag = "label-only"   # answer correct; misses gate on the intent label only
        else:
            tag = "behavior"
        flags = (f"places={'T' if r['places_used'] else 'F'} "
                 f"intent={'T' if r['intent_ok'] else 'F'}"
                 f"({r['got_intent']})" if not r["intent_ok"] else
                 f"places={'T' if r['places_used'] else 'F'} intent=T")
        reason = r["judge_reason"] or r["agent_error"] or "empty reply"
        fails.append(f"- {r['query_id']} [{r['expected_intent']}/{r['difficulty']}] "
                     f"({tag}) {flags} err={'T' if r['run_error'] else 'F'}: {reason}")
    n_label = sum(1 for r in records if not r["compound_pass"] and r["behavior_ok"] and not r["intent_ok"])
    n_beh = sum(1 for r in records if not r["compound_pass"] and not r["run_error"]
                and not (r["behavior_ok"] and not r["intent_ok"]))
    header = (f"({len(fails)} total: {n_beh} behaviour, {n_label} intent-label-only "
              f"[answer was correct], {sum(1 for r in records if r['run_error'])} run-error)")
    failures = header + "\n" + ("\n".join(fails) if fails else "- (none)")

    walls = [r["wall_s"] for r in records]
    median_wall = f"{statistics.median(walls):.1f}s" if walls else "n/a"
    total_wall = f"{sum(walls) / 60:.1f} min" if walls else "n/a"

    repl = {
        "{{DATE}}": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "{{AGENT_DESC}}": (f"real Jarvis pipeline (deterministic fast path + Atria ReAct agent "
                           f"fallback), app model `{agent_model}`, live Postgres+PostGIS+pgvector "
                           f"(map-db) and app DB"),
        "{{JUDGE_DESC}}": (f"`{judge_model}` ({temp_note}), response_format=json_object, "
                           f"separate from the agent model"),
        "{{HARNESS_DESC}}": ("scripts/pub_bench.py - per-case fresh chat session via "
                             "jarvis_chat.py loopback to /api/modules/tasco_jarvis_map/chat, "
                             f"bench user_id={BENCH_USER_ID}"),
        "{{N_CASES}}": str(total_cases),
        "{{LAST_ID}}": f"{total_cases:03d}",
        "{{SAMPLE_NOTE}}": sample_note,
        "{{BASELINE_BACKENDS}}": ", ".join(backends),
        "{{GATE_BACKEND}}": gate_backend,
        "{{INTENT_ACC}}": intent_acc,
        "{{POI_HIT1}}": poi1,
        "{{POI_HIT3}}": poi3,
        "{{CATEGORY_ACC}}": cat,
        "{{NORM_MATCH}}": norm,
        "{{CITY_PRECISION}}": cityprec,
        "{{ANCHORED_PASS}}": anch,
        "{{ENTITY_COV}}": pct(sum(1 for r in records if r["intent_ok"]), n),
        "{{LAT_P50}}": two_backend(lambda b: _lat_ms(baseline["search"][b]["latencies"], 0.50)),
        "{{LAT_P95}}": two_backend(lambda b: _lat_ms(baseline["search"][b]["latencies"], 0.95)),
        "{{COVERAGE_GAPS}}": str(len(baseline["search"][gate_backend]["gaps"])),
        "{{GATES}}": gates,
        "{{INTENT_BY_INTENT}}": intent_by_intent,
        "{{INTENT_BY_DIFFICULTY}}": intent_by_diff,
        "{{AGENT_PASS}}": pct(passed, n),
        "{{BEHAVIOR_OK}}": pct(behavior, n),
        "{{PLACES_USED}}": pct(places, n),
        "{{PATH_SPLIT}}": f"fast {fast}/{n} | agent {agentp}/{n}",
        "{{MAP_ACTION_OK}}": pct(mao, n),
        "{{NAME_RECALL_ANY}}": pct(rec_any, len(rec_cases)),
        "{{NAME_RECALL_IND}}": pct(rec_ind_hit, rec_ind_tot),
        "{{RUN_ERRORS}}": str(run_err),
        "{{JUDGE_ERRORS}}": str(judge_err),
        "{{PASS_BY_INTENT}}": pass_by_intent,
        "{{PASS_BY_DIFFICULTY}}": pass_by_diff,
        "{{FAILURES}}": failures,
        "{{CASES_RUN}}": str(n),
        "{{MEDIAN_WALL}}": median_wall,
        "{{TOTAL_WALL}}": total_wall,
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only first N cases (head slice; debug)")
    ap.add_argument("--sample", type=float, default=0.2,
                    help="fraction of the eval set to run, stratified by difficulty "
                         "(default 0.2 = a fast ~20%% quick check)")
    ap.add_argument("--full", action="store_true",
                    help="run all cases (regression sign-off / Proof of Done); overrides --sample")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed for the stratified sample (default: random each run, recorded)")
    ap.add_argument("--backend", choices=["json", "db", "both"], default="both",
                    help="baseline backend(s) (default both)")
    ap.add_argument("--agent-backend", choices=["json", "db"], default=None,
                    help="backend for the agent-level router calls (default: active .env)")
    ap.add_argument("--no-agent", action="store_true", help="baseline only (no agent/judge)")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE)
    ap.add_argument("--out", default=str(MODULE / "Tasks" / "MAP-PUBLIC-EVAL"))
    ap.add_argument("--render-only", action="store_true",
                    help="re-render REPORT.md from an existing raw_results.json "
                         "(recomputes the fast deterministic baseline; no agent/judge calls)")
    args = ap.parse_args()

    full_queries = load_json("eval_queries.json")["queries"]
    n_full = len(full_queries)
    sample_meta: dict | None = None
    if args.full or args.sample >= 1.0:
        queries = full_queries                       # full set (on demand)
    elif args.limit:
        queries = full_queries[: args.limit]         # legacy head slice (debug)
    else:
        seed = args.seed if args.seed is not None else random.SystemRandom().randrange(2 ** 32)
        queries, sample_meta = stratified_sample(full_queries, args.sample, seed)
    backends = ["json", "db"] if args.backend == "both" else [args.backend]
    gate_backend = args.agent_backend or _db.backend()
    if gate_backend not in backends:
        gate_backend = backends[-1]

    if args.render_only:
        out_dir = Path(args.out)
        raw = json.loads((out_dir / "raw_results.json").read_text(encoding="utf-8"))
        records = raw["cases"]
        prev_sample = raw["meta"].get("sample")
        # rebuild the exact case subset that ran, so the baseline matches the records
        ran_ids = {r["query_id"] for r in records}
        ran_queries = [q for q in full_queries if q["query_id"] in ran_ids]
        baseline = deterministic_baseline(ran_queries, backends)
        report = render_report(records, baseline, backends, gate_backend,
                               raw["meta"].get("agent_model", "app-default"),
                               raw["meta"].get("judge_model", DEFAULT_JUDGE),
                               "temperature not settable on gpt-5 family (default only)",
                               raw["meta"].get("n_full", n_full), prev_sample)
        (out_dir / "REPORT.md").write_text(report, encoding="utf-8")
        print(f"[pub_bench] re-rendered {out_dir / 'REPORT.md'} from raw_results.json",
              file=sys.stderr)
        return

    if sample_meta:
        pl = sample_meta["per_level"]
        print(f"[pub_bench] SAMPLE {len(queries)}/{n_full} cases, stratified by difficulty "
              f"({', '.join(f'{k} {pl[k]}' for k in pl)}), seed={sample_meta['seed']} "
              f"-- reproduce with --seed {sample_meta['seed']}; --full runs all {n_full}",
              file=sys.stderr)
    print(f"[pub_bench] {len(queries)} cases | baseline backends={backends} "
          f"| agent={'off' if args.no_agent else 'on'} | judge={args.judge_model}",
          file=sys.stderr)

    # 1. deterministic baseline
    print("[pub_bench] deterministic baseline ...", file=sys.stderr)
    baseline = deterministic_baseline(queries, backends)

    # 2. agent-level pass
    records: list[dict] = []
    agent_model = _db.env_get("ATRIA_MODEL", "app-default")
    temp_note = "temperature not settable on gpt-5 family (default only)"
    if not args.no_agent:
        os.environ["ATRIA_MAP_BACKEND"] = gate_backend  # router signals on production backend
        pois = load_json("pois.json")["pois"]
        cent, glob = city_centroids(pois)
        judge = make_judge(args.judge_model)
        for i, case in enumerate(queries, 1):
            vp = pick_viewport(case, cent, glob)
            rec = score_case(case, vp, judge)
            records.append(rec)
            flag = "PASS" if rec["compound_pass"] else "fail"
            print(f"  [{i:>2}/{len(queries)}] {rec['query_id']} {flag} "
                  f"({rec['source']}, {rec['wall_s']}s) intent={rec['got_intent']}",
                  file=sys.stderr)
    else:
        # baseline-only: still emit per-case router intent for the grouped tables
        os.environ["ATRIA_MAP_BACKEND"] = gate_backend
        for case in queries:
            router = cmd_search(SimpleNamespace(query=case["input_query"], limit=8,
                                                city=None, category=None))
            records.append({
                "query_id": case["query_id"], "input_query": case["input_query"],
                "difficulty": case.get("difficulty"),
                "expected_intent": case.get("expected_intent"),
                "got_intent": router.get("intent"),
                "intent_ok": router.get("intent") == case.get("expected_intent"),
                "places_used": bool(router.get("results")), "source": "n/a",
                "map_action_ok": False, "name_recall": (0, 0), "run_error": False,
                "behavior_ok": None, "judge_error": False, "judge_reason": "(no-agent)",
                "compound_pass": False, "confidence_score": router.get("confidence_score"),
                "reply": "", "action_types": [], "pinned": [], "wall_s": 0.0,
                "agent_error": None,
            })

    # 3. write report + raw results
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = render_report(records, baseline, backends, gate_backend,
                           agent_model, args.judge_model, temp_note, n_full, sample_meta)
    (out_dir / "REPORT.md").write_text(report, encoding="utf-8")
    (out_dir / "raw_results.json").write_text(
        json.dumps({
            "meta": {
                "generated_utc": datetime.now(timezone.utc).isoformat(),
                "n_cases": len(queries), "n_full": n_full, "sample": sample_meta,
                "baseline_backends": backends,
                "gate_backend": gate_backend, "agent_model": agent_model,
                "judge_model": args.judge_model, "no_agent": args.no_agent,
            },
            "cases": records,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[pub_bench] wrote {out_dir / 'REPORT.md'}", file=sys.stderr)
    if not args.no_agent:
        passed = sum(1 for r in records if r["compound_pass"])
        print(f"[pub_bench] agent-level compound pass: {pct(passed, len(records))}", file=sys.stderr)


if __name__ == "__main__":
    main()
