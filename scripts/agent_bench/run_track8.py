"""Run the Track 8 (maps assistant) agent-level bench.

Multi-turn cases: the sheet scripts prior turns inline ("User: ... | Assistant:
... | User: ..."); everything before the final user turn is seeded as history
and the final user turn is executed live. Writes raw JSONL transcripts.
Measure-only: results must never be used to tune retrieval.

Usage:
    .venv/bin/python scripts/agent_bench/run_track8.py [--limit N] [--only P001,P003]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.agent_bench.harness import load_env, run_batch  # noqa: E402

XLSX = REPO_ROOT / "mobility/track8/ai_maps_track3_dataset_participants.xlsx"
OUT_DIR = REPO_ROOT / "_local" / "agent_bench_2026-07-08"


def parse_turns(raw: str) -> tuple[list[dict[str, str]], str]:
    """Split the sheet's scripted conversation into (seeded_turns, final_user_turn).

    Format: "User: ..." or "User: ... | Assistant: ... | User: ..."
    (newlines in the cell were normalized; both newline and ' | ' separate turns).
    """
    parts = re.split(r"\s*\n\s*|\s+\|\s+", raw.strip())
    turns: list[dict[str, str]] = []
    for part in parts:
        m = re.match(r"^(User|Assistant)\s*:\s*(.*)$", part.strip(), re.IGNORECASE)
        if m:
            role = "user" if m.group(1).lower() == "user" else "assistant"
            turns.append({"role": role, "content": m.group(2).strip()})
        elif turns:
            turns[-1]["content"] += " " + part.strip()
    if not turns:
        return [], raw.strip()
    assert turns[-1]["role"] == "user", f"last scripted turn not a user turn: {raw!r}"
    return turns[:-1], turns[-1]["content"]


def load_cases() -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["Public_Evaluation"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(c) for c in rows[0]]  # header-row-1 layout
    cases = []
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        rec = dict(zip(header, [("" if c is None else str(c).strip()) for c in row]))
        cases.append(rec)
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", type=str, default=None, help="comma-separated eval_ids")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    load_env()
    cases = load_cases()
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["eval_id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "track8_transcripts.jsonl"
    done_ids = set()
    if out_path.exists():  # resume: skip already-run cases
        for line in out_path.read_text().splitlines():
            try:
                done_ids.add(json.loads(line)["eval_id"])
            except Exception:
                pass

    payloads = []
    for case in cases:
        if case["eval_id"] in done_ids:
            continue
        seeded, final_turn = parse_turns(case["conversation_turns"])
        payloads.append(
            {
                "final_user_turn": final_turn,
                "seeded_turns": seeded,
                "search_user_id": case["user_profile_id"],
                "meta": {
                    "eval_id": case["eval_id"],
                    "case": case,
                    "seeded_turns": seeded,
                    "final_user_turn": final_turn,
                },
            }
        )
    print(
        f"{len(payloads)} pending cases ({len(done_ids)} already done), " f"{args.workers} workers"
    )
    run_batch(payloads, out_path, id_key="eval_id", workers=args.workers)
    print(f"\nTranscripts: {out_path}")


if __name__ == "__main__":
    main()
