"""Run the Track 1 (enterprise knowledge) agent-level bench.

Drives the real agent through all Public_Evaluation questions, one fresh
session per case, identity injected per case. Writes raw JSONL transcripts.
Measure-only: results must never be used to tune retrieval.

Usage:
    .venv/bin/python scripts/agent_bench/run_track1.py [--limit N] [--only P001,P007]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_bench.harness import load_env, run_batch  # noqa: E402

XLSX = REPO_ROOT / "mobility/track1/ai_workspace_dataset_vietnamese_participants.xlsx"
OUT_DIR = REPO_ROOT / "_local" / "agent_bench_2026-07-08"


def load_cases() -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["Public_Evaluation"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c) for c in rows[2]]  # offset-2 layout: title, blank, header
    cases = []
    for row in rows[3:]:
        if not row or row[0] is None:
            continue
        rec = dict(zip(header, [("" if c is None else str(c).strip()) for c in row]))
        cases.append(rec)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", type=str, default=None, help="comma-separated question_ids")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    load_env()
    cases = load_cases()
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["question_id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "track1_transcripts.jsonl"
    done_ids = set()
    if out_path.exists():  # resume: skip already-run cases
        for line in out_path.read_text().splitlines():
            try:
                done_ids.add(json.loads(line)["question_id"])
            except Exception:
                pass

    payloads = [
        {
            "final_user_turn": case["question_vi"],
            "search_user_id": case["user_id"],
            "meta": {"question_id": case["question_id"], "case": case},
        }
        for case in cases
        if case["question_id"] not in done_ids
    ]
    print(
        f"{len(payloads)} pending cases ({len(done_ids)} already done), " f"{args.workers} workers"
    )
    run_batch(payloads, out_path, id_key="question_id", workers=args.workers)
    print(f"\nTranscripts: {out_path}")


if __name__ == "__main__":
    main()
