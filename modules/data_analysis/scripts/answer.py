#!/usr/bin/env python
"""One-shot question→answer pipeline.

Drives the full PRD loop (Planner → Data → Viz → Insight → Trace) for a
single user question and returns a TIGHT JSON summary the agent can
relay verbatim. Never echoes data rows; everything heavy is materialised
to disk and referenced by id.

Usage:
    da scripts/answer.py --slug <slug> --question "..." --sql "<DuckDB SQL>"

Output (≈ 400 bytes):
  {
    "artifact_id": "art_…",
    "chart_id":    "ch_…",
    "summary":     "…",
    "row_count":   12,
    "trace_id":    "tr_…"
  }

If you want the LLM to pick the SQL, do that one step *before* calling
this — then pass the chosen SQL here. This script does NOT call the LLM;
it just stitches together the deterministic Data/Viz/Insight steps so
the model does not have to remember the choreography.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import duck, workspace as ws  # noqa: E402


_KIND_PRIORITY = ["bar", "line", "scatter", "hist", "pie"]


def _pick_chart(columns: list[str], dtypes: list[str]) -> dict | None:
    nums, cats, dates = [], [], []
    for c, d in zip(columns, dtypes):
        u = (d or "").upper()
        if any(k in u for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT")):
            nums.append(c)
        elif "DATE" in u or "TIMESTAMP" in u:
            dates.append(c)
        else:
            cats.append(c)
    if dates and nums:
        return {"kind": "line", "x": dates[0], "y": nums[0]}
    if cats and nums:
        return {"kind": "bar", "x": cats[0], "y": nums[0]}
    if len(nums) >= 2:
        return {"kind": "scatter", "x": nums[0], "y": nums[1], "color": cats[0] if cats else None}
    if nums:
        return {"kind": "hist", "x": nums[0]}
    return None


def _summary(rows: list[list], columns: list[str], dtypes: list[str]) -> str:
    if not rows:
        return "Query returned 0 rows — nothing to summarise."
    cats, nums = [], []
    for c, d in zip(columns, dtypes):
        u = (d or "").upper()
        (nums if any(k in u for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL")) else cats).append(c)
    bits: list[str] = [f"Query returned {len(rows)} rows."]
    if cats and nums:
        ci, ni = columns.index(cats[0]), columns.index(nums[0])
        bucket: dict[str, float] = {}
        for r in rows:
            v = r[ni]
            if v is None:
                continue
            try:
                bucket[str(r[ci])] = bucket.get(str(r[ci]), 0.0) + float(v)
            except (TypeError, ValueError):
                continue
        if bucket:
            total = sum(bucket.values()) or 1.0
            top_k, top_v = max(bucket.items(), key=lambda kv: kv[1])
            bits.append(f"Top {cats[0]} by {nums[0]}: `{top_k}` "
                        f"({top_v:.2f}, {top_v / total:.0%} of total).")
    if nums:
        ni = columns.index(nums[0])
        vals = [float(r[ni]) for r in rows if isinstance(r[ni], (int, float))]
        if len(vals) >= 5:
            mean = statistics.fmean(vals)
            std = statistics.pstdev(vals)
            bits.append(f"{nums[0]}: mean={mean:.2f}, std={std:.2f}, min={min(vals):.2f}, max={max(vals):.2f}.")
    return " ".join(bits)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="One-shot answer pipeline.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--question", required=True, help="natural-language question for the trace")
    parser.add_argument("--sql", required=True, help="DuckDB SQL or @file.sql")
    parser.add_argument("--title", help="artifact title (defaults to first 60 chars of question)")
    parser.add_argument("--no-chart", action="store_true", help="skip viz step")
    args = parser.parse_args(argv[1:])

    proj = ws.require_project(args.slug)
    title = args.title or args.question[:60]

    # ── 1. Resolve SQL + register dataset views.
    sql = Path(args.sql[1:]).read_text(encoding="utf-8") if args.sql.startswith("@") else args.sql
    datasets = ws.list_datasets(args.slug)
    views = {d["name"]: Path(d["parquet"]) for d in datasets}

    # ── 2. execute + persist as artifact (Data Agent).
    result = duck.execute_sql(sql, views)
    art_id = ws.new_id("art_")
    dirs = ws.ensure_project_dirs(args.slug)
    art_parquet = dirs["artifacts"] / f"{art_id}.parquet"
    con = duck.connect()
    try:
        for name, path in views.items():
            safe = "".join(ch for ch in name if ch.isalnum() or ch == "_")
            p = str(path).replace("'", "''")
            con.execute(f"CREATE VIEW {safe} AS SELECT * FROM read_parquet('{p}')")
        out_p = str(art_parquet).replace("'", "''")
        con.execute(f"COPY ({sql}) TO '{out_p}' (FORMAT PARQUET)")
    finally:
        con.close()
    art_meta = {
        "id": art_id, "project": proj["slug"], "title": title,
        "question": args.question, "sql": sql,
        "columns": result["columns"], "dtypes": result["dtypes"],
        "row_count": result["row_count"], "parquet": str(art_parquet),
        "tags": [], "created_at": ws.now(),
        "source_datasets": list(views.keys()),
    }
    ws.save_artifact(args.slug, art_meta)

    # ── 3. recommend + save chart (Viz Agent).
    chart_id: str | None = None
    if not args.no_chart and result["row_count"] > 0:
        pick = _pick_chart(result["columns"], result["dtypes"])
        if pick:
            from chart import KINDS, _rows_to_records  # type: ignore
            records = _rows_to_records(result["columns"], result["rows"])
            kwargs = {k: v for k, v in {
                "x": pick.get("x"), "y": pick.get("y"),
                "color": pick.get("color"),
            }.items() if v is not None}
            if pick["kind"] == "pie":
                kwargs = {"group": pick["x"], "value": pick.get("y")}
            elif pick["kind"] == "hist":
                kwargs = {"x": pick["x"]}
            spec = KINDS[pick["kind"]](records, **kwargs)
            chart_id = ws.new_id("ch_")
            chart_meta = {
                "id": chart_id, "project": proj["slug"], "title": title,
                "kind": pick["kind"], "spec": spec,
                "vega_lib": "https://cdn.jsdelivr.net/npm/vega-lite@5",
                "artifact_id": art_id, "created_at": ws.now(),
            }
            ws.save_chart(args.slug, chart_meta)

    # ── 4. summarise (Insight Agent).
    summary = _summary(result["rows"], result["columns"], result["dtypes"])

    # ── 5. record trace.
    trace = {
        "id": ws.new_id("tr_"), "project": proj["slug"],
        "query": args.question, "plan": [],
        "actions": [{"agent": "data", "tool": "execute_sql"},
                    {"agent": "data", "tool": "save_artifact"}]
                   + ([{"agent": "viz", "tool": "save_chart"}] if chart_id else [])
                   + [{"agent": "insight", "tool": "summarise_results"}],
        "sql": sql,
        "tools_used": ["execute_sql", "save_artifact"]
                     + (["save_chart"] if chart_id else [])
                     + ["summarise_results"],
        "artifacts_created": [art_id],
        "result_summary": summary,
        "created_at": ws.now(),
    }
    ws.save_trace(args.slug, trace)

    # ── 6. tight receipt — never include rows.
    print(json.dumps({
        "artifact_id": art_id,
        "chart_id": chart_id,
        "row_count": result["row_count"],
        "summary": summary,
        "trace_id": trace["id"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
