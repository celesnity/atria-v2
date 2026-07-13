"""Score the Track 8 agent-level bench transcripts.

Axes:
- Deterministic: knowledge_search(source=places) usage; diacritics-normalized
  name-recall of expected_recommendations in the final answer (any / all).
- LLM judge: intent match; clarification behavior (for Clarification Dialog
  cases the agent should ASK, not guess); map-action equivalence — scored as
  its own axis so the missing route/geocoding facade shows up as a measured
  capability gap rather than being hidden.

Usage:
    .venv/bin/python scripts/agent_bench/score_track8.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_bench.harness import load_env  # noqa: E402
from scripts.agent_bench.judge import judge  # noqa: E402
from minder.core.context_engineering.search.normalize import normalize_for_search  # noqa: E402
from minder.core.context_engineering.search import pg  # noqa: E402


def _poi_names_norm() -> set[str]:
    rows = pg.fetch_all("SELECT name FROM pois", [])
    return {normalize_for_search(str(r["name"])) for r in rows}


OUT_DIR = REPO_ROOT / "_local" / "agent_bench_2026-07-08"
TRANSCRIPTS = OUT_DIR / "track8_transcripts.jsonl"
SCORES = OUT_DIR / "track8_scores.jsonl"

JUDGE_SYSTEM = """You grade one turn of a Vietnamese maps/POI assistant against expected behavior.
Reply with ONLY a JSON object:
{"intent_ok": true/false, "behavior_ok": true/false, "map_action_ok": true/false,
 "clarified": true/false, "reason": "<one or two sentences>"}
Definitions:
- intent_ok: the assistant understood the user's intent as described by expected_intent.
- behavior_ok: the assistant's reply substantively matches expected_response_summary
  (right kind of answer for this conversation category). For Clarification Dialog
  categories, behavior_ok requires the assistant to ASK a clarifying question (or
  explicitly disambiguate the options) rather than guessing one interpretation.
- map_action_ok: the assistant's actions (tool calls shown) plus reply are functionally
  equivalent to expected_map_action (e.g. a search with matching category/area filters,
  a route request, asking for the missing origin). If the expected action is a route/
  navigation action and the assistant only found the place but produced no route or
  explicit acknowledgment that routing is unavailable, mark false.
- clarified: the assistant asked the user a clarifying question this turn.
The conversation and answer are Vietnamese; grade substance, not language."""


def name_recall(expected_raw: str, answer: str) -> tuple[int, int]:
    expected = [e.strip() for e in expected_raw.split(";") if e.strip()]
    answer_norm = normalize_for_search(answer)
    hit = sum(1 for e in expected if normalize_for_search(e) in answer_norm)
    return hit, len(expected)


def score_record(record: dict, poi_names: set[str]) -> dict:
    case = record["case"]
    eid = record["eval_id"]
    answer = record["final_answer"] or ""

    ks_calls = [c for c in record["tool_calls"] if c["tool"] == "knowledge_search"]
    used_places = False
    for c in ks_calls:
        try:
            used_places = used_places or json.loads(c["args"]).get("source") == "places"
        except Exception:
            used_places = used_places or '"places"' in c["args"]
    profile_calls = [c for c in record["tool_calls"] if c["tool"] == "get_user_profile"]

    score: dict = {
        "eval_id": eid,
        "category": case["conversation_category"],
        "difficulty": case["difficulty"],
        "run_error": record["error"],
        "called_knowledge_search": bool(ks_calls),
        "used_places_source": used_places,
        "used_profile_tool": bool(profile_calls),
        "n_tool_calls": len(record["tool_calls"]),
    }

    expected = [e.strip() for e in case.get("expected_recommendations", "").split(";") if e.strip()]
    real = [e for e in expected if normalize_for_search(e) in poi_names]
    score["rec_generic"] = len(expected) - len(real)
    rec_hit = sum(1 for e in real if normalize_for_search(e) in normalize_for_search(answer))
    score["rec_hit"], score["rec_total"] = rec_hit, len(real)
    score["rec_any"] = rec_hit > 0 if real else None

    if record["error"] or not answer:
        score["judge"] = {"skipped": "run error or empty answer"}
        score["pass"] = False
        return score

    tools_desc = (
        "\n".join(f"- {c['tool']}({c['args'][:400]})" for c in record["tool_calls"])
        or "(no tool calls)"
    )
    convo = ""
    for turn in record.get("seeded_turns", []):
        convo += f"{turn['role'].capitalize()}: {turn['content']}\n"
    convo += f"User: {record['final_user_turn']}"

    verdict = judge(
        JUDGE_SYSTEM,
        f"conversation_category: {case['conversation_category']}\n"
        f"expected_intent: {case['expected_intent']}\n"
        f"expected_response_summary: {case['expected_response_summary']}\n"
        f"expected_map_action: {case['expected_map_action']}\n\n"
        f"Conversation:\n{convo}\n\n"
        f"Assistant tool calls this turn:\n{tools_desc}\n\n"
        f"Assistant reply:\n{answer[:6000]}",
    )
    score["judge"] = verdict
    score["gate"] = {
        "used_places_search": used_places,
        "intent_ok": bool(verdict.get("intent_ok")),
        "behavior_ok": bool(verdict.get("behavior_ok")),
    }
    score["pass"] = all(score["gate"].values())
    return score


def main() -> None:
    load_env()
    records = [json.loads(line) for line in TRANSCRIPTS.read_text().splitlines()]
    print(f"Scoring {len(records)} Track 8 transcripts...")
    poi_names = _poi_names_norm()

    scores = []
    with SCORES.open("w") as fh:
        for i, record in enumerate(records):
            s = score_record(record, poi_names)
            scores.append(s)
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
            fh.flush()
            print(
                f"[{i+1}/{len(records)}] {s['eval_id']} [{s['category']}] "
                f"pass={s['pass']} rec={s['rec_hit']}/{s['rec_total']} "
                f"map={s.get('judge', {}).get('map_action_ok')}"
            )

    def rate(xs, pred):
        n = sum(1 for x in xs if pred(x))
        return f"{n}/{len(xs)}"

    print("\n=== Track 8 agent-level summary ===")
    print(f"pass (compound gate):     {rate(scores, lambda s: s['pass'])}")
    print(f"knowledge_search called:  {rate(scores, lambda s: s['called_knowledge_search'])}")
    print(f"places source used:       {rate(scores, lambda s: s['used_places_source'])}")
    scored_rec = [s for s in scores if s["rec_total"]]
    print(f"rec name-recall (any):    {rate(scored_rec, lambda s: s['rec_any'])}")
    total_hit = sum(s["rec_hit"] for s in scored_rec)
    total_names = sum(s["rec_total"] for s in scored_rec)
    print(f"rec name-recall (names):  {total_hit}/{total_names}")
    total_generic = sum(s["rec_generic"] for s in scores)
    print(f"rec expected (generic):   {total_generic}  [excluded from recall, not real POI names]")
    print(
        f"map_action_ok:            "
        f"{rate(scores, lambda s: s.get('judge', {}).get('map_action_ok'))}"
    )

    by_cat: dict[str, list] = {}
    for s in scores:
        by_cat.setdefault(s["category"], []).append(s)
    print("\nBy category:")
    for cat, xs in sorted(by_cat.items()):
        print(f"  {cat:26s} {rate(xs, lambda s: s['pass'])}")
    print(f"\nScores: {SCORES}")


if __name__ == "__main__":
    main()
