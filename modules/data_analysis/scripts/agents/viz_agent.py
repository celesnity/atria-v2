#!/usr/bin/env python
"""Visualization Agent (PRD §5.5.3).

Tools:
  recommend_charts(artifact_id) — propose chart types from the artifact's
      result-table shape. Pure inspection, no rendering.
  generate_chart(artifact_id, kind, x, y, ...) — build a Vega-Lite spec
      from the artifact's Parquet rows.
  save_chart(...) — persist a chart, linked to its source artifact and
      project (FR-VIZ-03).

The agent does NOT interpret data or draw business conclusions
(FR-VIZ-04) — that responsibility belongs to the Insight Agent.

(PRD spec says Matplotlib; we render via Vega-Lite in the browser block
to keep the host CLI dependency-free. The artifact's Parquet remains the
canonical chartable surface either way.)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import duck, workspace as ws  # noqa: E402


def _artifact(slug: str, art_id: str) -> dict:
    a = ws.get_artifact(slug, art_id) or next(
        (x for x in ws.list_artifacts(slug) if x["id"].startswith(art_id)), None
    )
    if not a:
        raise SystemExit(f"ERROR: artifact not found: {art_id}")
    return a


def _classify_columns(artifact: dict) -> dict[str, list[str]]:
    num, cat, date = [], [], []
    for name, dtype in zip(artifact["columns"], artifact["dtypes"]):
        u = dtype.upper()
        if any(k in u for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT")):
            num.append(name)
        elif "DATE" in u or "TIMESTAMP" in u:
            date.append(name)
        else:
            cat.append(name)
    return {"num": num, "cat": cat, "date": date}


def cmd_recommend(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    a = _artifact(args.slug, args.artifact_id)
    cols = _classify_columns(a)
    recs: list[dict] = []
    if cols["date"] and cols["num"]:
        recs.append({"kind": "line", "x": cols["date"][0], "y": cols["num"][0],
                     "why": "Time-series — date axis + numeric metric."})
    if cols["cat"] and cols["num"]:
        recs.append({"kind": "bar", "x": cols["cat"][0], "y": cols["num"][0],
                     "why": "Categorical breakdown of a numeric metric."})
        recs.append({"kind": "pie", "x": cols["cat"][0], "y": cols["num"][0],
                     "why": "Share-of-total view across categories."})
    if len(cols["num"]) >= 2:
        recs.append({"kind": "scatter", "x": cols["num"][0], "y": cols["num"][1],
                     "color": cols["cat"][0] if cols["cat"] else None,
                     "why": "Two numeric variables — investigate correlation."})
    if cols["num"]:
        recs.append({"kind": "hist", "x": cols["num"][0],
                     "why": "Distribution + outliers of the primary metric."})
    print(json.dumps({"artifact_id": a["id"], "recommendations": recs}, ensure_ascii=False))
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    a = _artifact(args.slug, args.artifact_id)
    rows = duck.execute_sql("SELECT * FROM art", {"art": Path(a["parquet"])})

    # Lazy import of the existing chart-spec builder.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from chart import KINDS, _rows_to_records  # type: ignore

    records = _rows_to_records(rows["columns"], rows["rows"])
    builder = KINDS[args.kind]
    kwargs: dict = {}
    if args.kind in ("bar", "line", "area"):
        kwargs = {"x": args.x, "y": args.y}
    elif args.kind == "scatter":
        kwargs = {"x": args.x, "y": args.y, "color": args.color}
    elif args.kind == "hist":
        kwargs = {"x": args.x, "bins": args.bins}
    elif args.kind == "pie":
        kwargs = {"group": args.x, "value": args.y}
    elif args.kind == "heatmap":
        kwargs = {"x": args.x, "y": args.y, "value": args.color}
    spec = builder(records, **{k: v for k, v in kwargs.items() if v is not None})

    chart_meta = {
        "id": ws.new_id("ch_"),
        "project": args.slug,
        "title": args.title or spec.get("title", args.kind),
        "kind": args.kind,
        "spec": spec,
        "vega_lib": "https://cdn.jsdelivr.net/npm/vega-lite@5",
        "artifact_id": a["id"],
        "created_at": ws.now(),
    }
    if args.save:
        ws.save_chart(args.slug, chart_meta)
        # Short receipt — never echo the spec (it embeds full row data).
        n_rows = len(spec.get("data", {}).get("values", []))
        print(json.dumps({
            "saved_chart": chart_meta["id"], "artifact_id": a["id"],
            "kind": args.kind, "rows_embedded": n_rows,
        }, ensure_ascii=False))
    else:
        # Elide data so stdout stays small. Pass --save to materialise.
        elided = dict(chart_meta)
        elided["spec"] = {k: v for k, v in spec.items() if k != "data"}
        elided["spec"]["data"] = {"values": "<<elided — use --save>>"}
        elided["rows_elided"] = len(spec.get("data", {}).get("values", []))
        print(json.dumps(elided, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Visualization Agent.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("recommend", help="recommend chart types for an artifact (FR-VIZ-01)")
    p_rec.add_argument("--slug", required=True)
    p_rec.add_argument("--artifact-id", required=True)
    p_rec.set_defaults(fn=cmd_recommend)

    p_gen = sub.add_parser("generate", help="build a chart spec from an artifact (FR-VIZ-02)")
    p_gen.add_argument("--slug", required=True)
    p_gen.add_argument("--artifact-id", required=True)
    p_gen.add_argument("--kind", required=True, choices=["bar", "line", "area", "scatter", "hist", "pie", "heatmap"])
    p_gen.add_argument("--x")
    p_gen.add_argument("--y")
    p_gen.add_argument("--color")
    p_gen.add_argument("--bins", type=int, default=20)
    p_gen.add_argument("--title")
    p_gen.add_argument("--save", action="store_true", help="persist chart in the project (FR-VIZ-03)")
    p_gen.add_argument("--json", action="store_true")
    p_gen.set_defaults(fn=cmd_generate)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
