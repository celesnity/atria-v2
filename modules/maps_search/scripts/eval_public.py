"""Score the places provider against the Track 8 Public_Evaluation sheet.

Retrieval-only baseline: takes the LAST user turn of each conversation as the
query (multi-turn context assembly is the agent's job, out of scope here) and
measures recall of expected_recommendations names in the top-k results.

Usage:
    python modules/maps_search/scripts/eval_public.py \
        --xlsx mobility/track8/ai_maps_track3_dataset_participants.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import openpyxl

# Repo root, so `atria` resolves when this file is run directly (as a script,
# rather than through a test runner that already puts the repo root on
# sys.path). Needed regardless of whether atria is pip-installed editable.
# Must land on sys.path before `search_provider` is imported below, since
# search_provider.py itself imports `atria.*` at module load time.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for search_provider
from search_provider import get_provider  # noqa: E402

from atria.core.context_engineering.search.normalize import normalize_for_search  # noqa: E402
from atria.core.context_engineering.search.types import SearchContext  # noqa: E402


def _eval_rows(xlsx: str) -> list[dict[str, Any]]:
    """Read the Track 8 Public_Evaluation sheet (header row 1) into dicts.

    Args:
        xlsx: Path to the Track 8 participants workbook.

    Returns:
        One dict per data row, mapping header column name to cell value.
    """
    sheet = openpyxl.load_workbook(xlsx, read_only=True)["Public_Evaluation"]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c) for c in rows[0]]
    return [
        {header[i]: raw[i] for i in range(len(header))}
        for raw in rows[1:]
        if raw and any(c is not None for c in raw)
    ]


def _last_user_turn(conversation: str) -> str:
    """Extract the final `User:`-prefixed line from a conversation transcript.

    Args:
        conversation: The full multi-turn conversation text.

    Returns:
        The last user turn with the `User:` prefix stripped, or the whole
        conversation string if no `User:`-prefixed line is found.
    """
    turns = [t.strip() for t in str(conversation).splitlines() if t.strip().startswith("User:")]
    return turns[-1].removeprefix("User:").strip() if turns else str(conversation)


def main() -> None:
    """Run the Track 8 retrieval baseline and print recommendation recall@k.

    Args:
        None. Arguments are parsed from `sys.argv` via argparse (`--xlsx`,
        `--k`).

    Returns:
        None. Prints the headline metric and a per-question miss line for
        each expected recommendation not found to stdout.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    provider = get_provider()
    total_expected = total_found = rows_scored = 0
    misses: list[str] = []

    for row in _eval_rows(args.xlsx):
        expected_raw = str(row.get("expected_recommendations") or "").strip()
        if not expected_raw:
            continue
        expected_names = [n.strip() for n in expected_raw.split(";") if n.strip()]
        query = _last_user_turn(str(row["conversation_turns"]))
        results = provider.search(query, {}, args.k, SearchContext())
        returned_norm = [normalize_for_search(hit.title) for hit in results.hits]
        rows_scored += 1
        for name in expected_names:
            total_expected += 1
            name_norm = normalize_for_search(name)
            if any(name_norm in r or r in name_norm for r in returned_norm):
                total_found += 1
            else:
                misses.append(f"MISS  {row['eval_id']} expected {name!r} for query {query!r}")

    print(f"Track 8 retrieval baseline (k={args.k}, {rows_scored} rows scored)")
    print(
        f"  recommendation recall@{args.k}: {total_found}/{total_expected} "
        f"= {total_found / max(total_expected, 1):.2%}"
    )
    print("  NOTE: single-turn retrieval baseline; expected_recommendations may be")
    print("  free-text rather than exact POI names — inspect misses before judging.")
    for line in misses:
        print(f"  {line}")


if __name__ == "__main__":
    main()
