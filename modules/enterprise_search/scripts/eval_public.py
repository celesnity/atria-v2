"""Score the documents provider against the Track 1 Public_Evaluation sheet.

Retrieval-only metrics (no LLM answer generation):
  - allow_hit@5: for Allow rows, expected_document_id appears in top-5 hits.
  - deny_leak:   for Deny rows, expected_document_id appears in ANY hit (must be 0).

Usage:
    python modules/enterprise_search/scripts/eval_public.py \
        --xlsx mobility/track1/ai_workspace_dataset_vietnamese_participants.xlsx
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

from atria.core.context_engineering.search.types import SearchContext  # noqa: E402

_HEADER_ROW_OFFSET = 2  # sheet: title row, blank row, header row, data...


def _eval_rows(xlsx: str) -> list[dict[str, Any]]:
    """Read the Track 1 Public_Evaluation sheet into dicts keyed by its header row.

    Args:
        xlsx: Path to the Track 1 participants workbook.

    Returns:
        One dict per data row, mapping header column name to cell value.
    """
    sheet = openpyxl.load_workbook(xlsx, read_only=True)["Public_Evaluation"]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(c) for c in rows[_HEADER_ROW_OFFSET]]
    return [
        {header[i]: raw[i] for i in range(len(header))}
        for raw in rows[_HEADER_ROW_OFFSET + 1 :]
        if raw and any(c is not None for c in raw)
    ]


def main() -> None:
    """Run the Track 1 retrieval baseline and print allow_hit@k / deny_leaks.

    Args:
        None. Arguments are parsed from `sys.argv` via argparse (`--xlsx`,
        `--k`).

    Returns:
        None. Prints the headline metrics and a per-question miss/leak line
        for each failure to stdout.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    provider = get_provider()
    allow_total = allow_hits = deny_total = deny_leaks = 0
    failures: list[str] = []

    for row in _eval_rows(args.xlsx):
        question = str(row["question_vi"])
        expected_doc = str(row.get("expected_document_id") or "")
        context = SearchContext(user_id=str(row["user_id"]))
        results = provider.search(question, {}, args.k, context)
        returned = [hit.metadata["document_id"] for hit in results.hits]
        if str(row["expected_permission"]) == "Allow":
            allow_total += 1
            if expected_doc and expected_doc in returned:
                allow_hits += 1
            else:
                failures.append(
                    f"MISS  {row['question_id']} expected={expected_doc} got={returned}"
                )
        else:
            deny_total += 1
            if expected_doc and expected_doc in returned:
                deny_leaks += 1
                failures.append(f"LEAK  {row['question_id']} {expected_doc} surfaced: {returned}")

    print(f"Track 1 retrieval baseline (k={args.k})")
    print(
        f"  allow_hit@{args.k}: {allow_hits}/{allow_total} = {allow_hits / max(allow_total, 1):.2%}"
    )
    print(f"  deny_leaks:   {deny_leaks}/{deny_total} (MUST be 0)")
    for line in failures:
        print(f"  {line}")


if __name__ == "__main__":
    main()
