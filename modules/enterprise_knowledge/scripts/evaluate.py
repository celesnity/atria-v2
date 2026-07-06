"""Offline evaluation over the dataset's Public_Evaluation cases.

For each labeled case, checks two things against a ``query_fn``:
- permission_ok: an Allow case returns >=1 hit; a Deny case returns none.
- doc_recall_hit: the expected_document_id appears among returned hits (Allow only).

Used to prove graph-augmented retrieval keeps every Allow/Deny outcome and does
not reduce expected-document recall vs. the vector-only baseline.
"""

from __future__ import annotations

import csv
from typing import Callable


def load_cases(path: str) -> list[dict]:
    """Load evaluation cases from a Public_Evaluation CSV export."""
    with open(path, newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def run_case(case: dict, query_fn: Callable[[str, str], dict]) -> dict:
    """Score one case against ``query_fn(question_vi, user_id) -> {"hits": [...]}``."""
    result = query_fn(case["question_vi"], case["user_id"])
    hits = result.get("hits", [])
    doc_ids = {h.get("doc_id") for h in hits}
    is_allow = case["expected_permission"] == "Allow"
    permission_ok = bool(hits) == is_allow
    doc_recall_hit = is_allow and case.get("expected_document_id") in doc_ids
    return {
        "question_id": case.get("question_id"),
        "permission_ok": permission_ok,
        "doc_recall_hit": doc_recall_hit,
    }


def summarize(results: list[dict]) -> dict:
    """Aggregate case results into totals + regression/recall counts."""
    return {
        "total": len(results),
        "permission_regressions": sum(1 for r in results if not r["permission_ok"]),
        "recall_hits": sum(1 for r in results if r["doc_recall_hit"]),
    }
