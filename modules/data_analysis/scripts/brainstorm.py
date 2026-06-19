#!/usr/bin/env python
"""Brainstorming agent-loop primer.

Given a data file, profile it and emit a structured brief the agent can
consume to drive its `/brainstorming` loop. Output is a stable JSON blob
listing: dataset summary, candidate questions, chart ideas, hypotheses
to test, and concrete next CLI commands.

The agent treats the output as the seed state for an iterative loop:
    profile → pick an idea → build chart → derive insight → pin → repeat
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analyze import load, profile_columns, derive_insights  # noqa: E402
from chart import suggest_charts  # noqa: E402


def _questions(profile: list[dict]) -> list[str]:
    num = [c["name"] for c in profile if c["type"] == "number"]
    cat = [c["name"] for c in profile if c["type"] == "string" and 2 <= c["unique"] <= 25]
    date = [c["name"] for c in profile if c["type"] == "date"]
    qs: list[str] = []
    if date and num:
        qs.append(f"How does {num[0]} evolve over {date[0]}? Any seasonality or break-points?")
    if cat and num:
        qs.append(f"Which {cat[0]} contributes most to {num[0]}? Is the distribution Pareto-like?")
    if len(num) >= 2:
        qs.append(f"Is {num[0]} correlated with {num[1]}? Are there clusters by {cat[0] if cat else 'a category'}?")
    for c in profile:
        if c["type"] == "number" and c.get("stats", {}).get("std", 0) > 0:
            qs.append(f"What drives the outliers in {c['name']}?")
            break
    for c in profile:
        if c["non_null"] < c["n"] * 0.7:
            qs.append(f"Why is {c['name']} so often empty — collection issue or true absence?")
            break
    return qs[:8]


def _hypotheses(profile: list[dict], insights: list[dict]) -> list[str]:
    hyps: list[str] = []
    for ins in insights:
        if ins["kind"] == "skew":
            hyps.append(f"`{ins['column']}` skew is driven by a small subgroup — segment and re-plot.")
        elif ins["kind"] == "outliers":
            hyps.append(f"Outliers in `{ins['column']}` are real events (not data errors) — confirm by joining with category dimension.")
        elif ins["kind"] == "missing" and ins.get("severity") in ("medium", "high"):
            hyps.append(f"Missing `{ins['column']}` correlates with a specific category or time window.")
        elif ins["kind"] == "timeseries":
            hyps.append("Time-series shows a structural break or trend reversal worth annotating.")
    return hyps[:6]


def _next_actions(path: str) -> list[str]:
    return [
        f"python <modules>/data_analysis/scripts/chart.py suggest --path '{path}'",
        f"python <modules>/data_analysis/scripts/chart.py spec --path '{path}' --kind bar --x <cat> --y <metric> --save bar1.json",
        f"python <modules>/data_analysis/scripts/dashboard.py pin --spec bar1.json --title 'Top categories'",
        f"python <modules>/data_analysis/scripts/analyze.py insights --path '{path}' --text",
    ]


def build_brief(path: str, sheet) -> dict:
    header, rows, p = load(path, sheet=sheet)
    profile = profile_columns(header, rows)
    insights = derive_insights(header, rows, profile)
    return {
        "path": str(p),
        "shape": {"rows": len(rows), "columns": len(header)},
        "columns": [{"name": c["name"], "type": c["type"], "non_null": c["non_null"]} for c in profile],
        "insights": insights,
        "questions": _questions(profile),
        "hypotheses": _hypotheses(profile, insights),
        "chart_ideas": suggest_charts(profile),
        "next_actions": _next_actions(str(p)),
    }


def _push_block(brief: dict, title: str) -> int:
    session_id = os.environ.get("ATRIA_SESSION_ID")
    api_base = os.environ.get("ATRIA_API_BASE")
    if not session_id or not api_base:
        print("ERROR: ATRIA_SESSION_ID / ATRIA_API_BASE not set.", file=sys.stderr)
        return 2
    body = json.dumps({
        "session_id": session_id,
        "module": "data_analysis",
        "block": "brainstorm",
        "props": {"brief": brief},
        "title": title,
    }).encode("utf-8")
    req = urllib.request.Request(f"{api_base.rstrip('/')}/api/blocks/push", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"ERROR: push failed ({exc.code}): {exc.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: cannot reach {api_base}: {exc.reason}", file=sys.stderr)
        return 1
    print(f"pushed brainstorm block: id={payload.get('block_id')}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Brainstorming primer for /brainstorming loop.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--push", action="store_true", help="also push a brainstorm block to chat")
    parser.add_argument("--title", default="Brainstorming brief")
    args = parser.parse_args(argv[1:])
    sheet = int(args.sheet) if args.sheet and args.sheet.isdigit() else args.sheet
    brief = build_brief(args.path, sheet)
    if args.push:
        rc = _push_block(brief, args.title)
        if rc != 0:
            return rc
    print(json.dumps(brief, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
