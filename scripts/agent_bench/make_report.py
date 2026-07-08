"""Consolidate agent-bench scores into a markdown report.

Usage:
    .venv/bin/python scripts/agent_bench/make_report.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "_local" / "agent_bench_2026-07-08"

RETRIEVAL_BASELINE = {
    "track1": "allow_hit@5 = 93.0% (40/43), deny retrieval leaks: 0 code-attributable",
    "track2": "recall@10 = 76.6% (36/47, understated by multi-ID scoring artifact)",
}


def load(name: str) -> list[dict]:
    path = OUT_DIR / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"


def main() -> None:
    t1 = load("track1_scores.jsonl")
    t8 = load("track8_scores.jsonl")
    t1_raw = load("track1_transcripts.jsonl")
    t8_raw = load("track8_transcripts.jsonl")

    agent_model = os.environ.get("ATRIA_MODEL", "?")
    judge_model = os.environ.get("JUDGE_MODEL", "openai/gpt-4o-mini")

    lines: list[str] = []
    add = lines.append
    add("# Agent-Level Bench Report — 2026-07-08")
    add("")
    add(
        f"- Agent under test: real Atria ReAct loop, model `{agent_model}` "
        "(bench override — .env's `openrouter/free` proved non-viable, see "
        "findings), live Postgres+Qdrant stores"
    )
    add(f"- Judge: `{judge_model}` at temperature 0 (separate from agent model)")
    add(
        "- Harness: scripts/agent_bench/ — headless stack per deps_builder.py, "
        "per-case identity via ATRIA_SEARCH_USER_ID, one fresh session per case, "
        "assistant-agent deployment (suite.agents.assistant)"
    )
    add("- Discipline: measure-only. No retrieval/prompt tuning from these results.")
    add("")

    if t1:
        allow = [s for s in t1 if s["expected_permission"] == "Allow"]
        deny = [s for s in t1 if s["expected_permission"] == "Deny"]
        deny_adj = [s for s in deny if not s["dataset_conflict"]]
        errors = [s for s in t1 if s["run_error"]]
        add("## Track 1 — Enterprise Knowledge (50 cases)")
        add("")
        add(f"- Retrieval-only baseline: {RETRIEVAL_BASELINE['track1']}")
        add(
            f"- knowledge_search called: "
            f"{pct(sum(1 for s in t1 if s['called_knowledge_search']), len(t1))}"
        )
        add(
            f"- Allow answers judged correct: "
            f"{pct(sum(1 for s in allow if s['pass']), len(allow))}"
        )
        add(
            f"- Allow agent-level retrieval hit: "
            f"{pct(sum(1 for s in allow if s['retrieval_hit']), len(allow))}"
        )
        add(
            f"- Deny handled correctly (raw): "
            f"{pct(sum(1 for s in deny if s['pass']), len(deny))}"
        )
        add(
            f"- Deny handled correctly (adjusted for P035 dataset conflict): "
            f"{pct(sum(1 for s in deny_adj if s['pass']), len(deny_adj))}"
        )
        leaks = [s["question_id"] for s in deny if s.get("judge", {}).get("leaked")]
        add(f"- Deny answer-level leaks: {', '.join(leaks) if leaks else 'none'}")
        rleaks = [s["question_id"] for s in deny if s["retrieval_leak"]]
        add(
            f"- Deny retrieval-level leaks (expected doc in tool results): "
            f"{', '.join(rleaks) if rleaks else 'none'}"
        )
        add(
            f"- Run errors (crashes/aborts): "
            f"{len(errors)}{' — ' + ', '.join(s['question_id'] for s in errors) if errors else ''}"
        )
        add("")
        by_type: dict[str, list] = {}
        for s in allow:
            by_type.setdefault(s["answer_type"], []).append(s)
        add("Allow pass rate by answer_type:")
        for typ, xs in sorted(by_type.items()):
            add(f"- {typ}: {pct(sum(1 for s in xs if s['pass']), len(xs))}")
        add("")
        fails = [s for s in t1 if not s["pass"]]
        if fails:
            add("Failures:")
            for s in fails:
                reason = s.get("judge", {}).get("reason") or s.get("judge", {}).get("skipped", "")
                add(
                    f"- {s['question_id']} [{s['expected_permission']}/"
                    f"{s['answer_type']}] ks={s['called_knowledge_search']} "
                    f"hit={s['retrieval_hit']} err={bool(s['run_error'])}: {reason}"
                )
        add("")

    if t8:
        errors8 = [s for s in t8 if s["run_error"]]
        scored_rec = [s for s in t8 if s["rec_total"]]
        add("## Track 8 — Maps Assistant (30 cases)")
        add("")
        add(f"- Retrieval-only baseline: {RETRIEVAL_BASELINE['track2']}")
        add(f"- Pass (intent + behavior): {pct(sum(1 for s in t8 if s['pass']), len(t8))}")
        add(
            f"- knowledge_search called: "
            f"{pct(sum(1 for s in t8 if s['called_knowledge_search']), len(t8))}"
        )
        add(
            f"- places source used: "
            f"{pct(sum(1 for s in t8 if s['used_places_source']), len(t8))}"
        )
        add(
            f"- Recommendation name-recall (any expected name in answer): "
            f"{pct(sum(1 for s in scored_rec if s['rec_any']), len(scored_rec))}"
        )
        add(
            f"- Recommendation name-recall (individual names): "
            f"{pct(sum(s['rec_hit'] for s in scored_rec), sum(s['rec_total'] for s in scored_rec))}"
        )
        add(
            f"- map_action_ok (incl. route capability gap): "
            f"{pct(sum(1 for s in t8 if s.get('judge', {}).get('map_action_ok')), len(t8))}"
        )
        add(
            f"- Run errors: {len(errors8)}"
            f"{' — ' + ', '.join(s['eval_id'] for s in errors8) if errors8 else ''}"
        )
        add("")
        by_cat: dict[str, list] = {}
        for s in t8:
            by_cat.setdefault(s["category"], []).append(s)
        add("Pass rate by conversation category:")
        for cat, xs in sorted(by_cat.items()):
            add(f"- {cat}: {pct(sum(1 for s in xs if s['pass']), len(xs))}")
        add("")
        fails8 = [s for s in t8 if not s["pass"]]
        if fails8:
            add("Failures:")
            for s in fails8:
                reason = s.get("judge", {}).get("reason") or s.get("judge", {}).get("skipped", "")
                add(
                    f"- {s['eval_id']} [{s['category']}] ks={s['called_knowledge_search']} "
                    f"rec={s['rec_hit']}/{s['rec_total']} err={bool(s['run_error'])}: {reason}"
                )
        add("")

    if t1_raw or t8_raw:
        walls = [r["wall_ms"] for r in (t1_raw + t8_raw) if r.get("wall_ms")]
        if walls:
            add("## Runtime")
            add("")
            add(f"- Cases run: {len(t1_raw)} (T1) + {len(t8_raw)} (T8)")
            add(
                f"- Median wall per case: {sorted(walls)[len(walls) // 2] / 1000:.1f}s; "
                f"total: {sum(walls) / 60000:.1f} min"
            )
            add("")

    report_path = OUT_DIR / "report.md"
    report_path.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nReport written: {report_path}")


if __name__ == "__main__":
    main()
