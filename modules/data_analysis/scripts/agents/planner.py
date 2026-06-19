#!/usr/bin/env python
"""Planner Agent (PRD §5.5.1).

Produces a draft execution plan from a user query against a project's
catalog of datasets and artifacts. The plan is a list of typed steps —
each step is a tool call the main LLM can decide to execute, reorder, or
skip. We DO NOT branch on if/else flags here; we just propose. The
agent (main loop in the host CLI) chooses the next step.

Outputs JSON of the form:

{
  "query": "…",
  "ambiguities": ["…"],          # FR-PLAN-03 (clarifying questions)
  "retrieved_artifacts": [...],  # FR-PLAN-04
  "steps": [ {"agent": "data", "tool": "execute_sql", "args": {...}}, ... ]
}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import workspace as ws  # noqa: E402
from core.retrieve import retrieve  # noqa: E402


def _clarify(query: str, datasets: list[dict], artifacts: list[dict]) -> list[str]:
    q = query.lower()
    asks: list[str] = []
    if not datasets:
        asks.append("No datasets are uploaded yet. Which file should I ingest first?")
        return asks
    if any(k in q for k in ("recent", "latest", "this month", "last week")) and not any(
        any("date" in c["name"].lower() or "time" in c["name"].lower() for c in d.get("columns", []))
        for d in datasets
    ):
        asks.append("Question implies a time window, but no date/time column was detected. Which column carries the timestamp?")
    metric_words = ("revenue", "cost", "count", "rate", "yield", "defect", "duration")
    if any(w in q for w in metric_words):
        numeric = [c["name"] for d in datasets for c in d.get("columns", []) if "INT" in c["type"].upper() or "DOUBLE" in c["type"].upper() or "DECIMAL" in c["type"].upper()]
        if not numeric:
            asks.append("Question asks for a metric but no numeric columns are present. Should I derive one?")
    return asks


def _plan_steps(query: str, datasets: list[dict], retrieved: list[dict]) -> list[dict]:
    steps: list[dict] = []

    # Always start by pulling schemas so the Data Agent has context.
    steps.append({
        "agent": "data",
        "tool": "retrieve_metadata",
        "args": {"dataset_ids": [d["id"] for d in datasets]},
        "why": "Load schema + profile for all candidate datasets.",
    })

    if len(datasets) >= 2:
        steps.append({
            "agent": "data",
            "tool": "discover_relationships",
            "args": {},
            "why": "Find join keys with confidence scores before any cross-dataset SQL.",
        })

    if retrieved:
        steps.append({
            "agent": "planner",
            "tool": "reuse_artifact_decision",
            "args": {"candidates": [a["id"] for a in retrieved]},
            "why": "A prior artifact may already answer this question — reuse before recomputing (FR-ART-02).",
        })

    steps.append({
        "agent": "data",
        "tool": "execute_sql",
        "args": {"sql": "<<LLM-generated DuckDB SQL>>"},
        "why": "Translate the question into DuckDB SQL and execute against parquet views.",
    })
    steps.append({
        "agent": "data",
        "tool": "save_artifact",
        "args": {"title": "<<short title>>", "question": query},
        "why": "Persist the result so future questions can recall it (FR-DATA-05).",
    })
    steps.append({
        "agent": "viz",
        "tool": "recommend_charts",
        "args": {"artifact_id": "<<from previous step>>"},
        "why": "Recommend chart types matched to the result table shape (FR-VIZ-01).",
    })
    steps.append({
        "agent": "insight",
        "tool": "summarise_results",
        "args": {"artifact_id": "<<from previous step>>"},
        "why": "Surface anomalies, key contributors, correlations (FR-INS-01..03).",
    })
    return steps


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Planner Agent: produce an execution plan.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--query", required=True, help="user's natural-language question")
    parser.add_argument("--top-k", type=int, default=3, help="how many prior artifacts to surface")
    args = parser.parse_args(argv[1:])

    ws.require_project(args.slug)
    datasets = ws.list_datasets(args.slug)
    artifacts = ws.list_artifacts(args.slug)
    retrieved = [a for a, _ in retrieve(args.query, artifacts, top_k=args.top_k)]

    out = {
        "query": args.query,
        "ambiguities": _clarify(args.query, datasets, artifacts),
        "retrieved_artifacts": [
            {"id": a["id"], "title": a.get("title"), "row_count": a.get("row_count")}
            for a in retrieved
        ],
        "datasets_considered": [{"id": d["id"], "name": d["name"]} for d in datasets],
        "steps": _plan_steps(args.query, datasets, retrieved),
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
