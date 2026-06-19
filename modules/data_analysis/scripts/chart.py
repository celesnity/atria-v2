#!/usr/bin/env python
"""Build Vega-Lite chart specs from CSV/Excel files.

Subcommands: spec, suggest.

`spec` builds one chart spec for a chosen kind (bar, line, scatter, hist,
pie, area, heatmap) and prints it as JSON.

`suggest` profiles the data and proposes a ranked list of chart ideas
the agent can iterate through during /brainstorming.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from analyze import load, profile_columns, _to_num  # noqa: E402


VEGA_LIB_URL = "https://cdn.jsdelivr.net/npm/vega-lite@5"


# ─── Aggregation helpers ─────────────────────────────────────────────────

def _rows_to_records(header: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        d = {h: (r[i] if i < len(r) else "") for i, h in enumerate(header)}
        out.append(d)
    return out


def _coerce_num(records: list[dict[str, Any]], col: str) -> None:
    for r in records:
        n = _to_num(r.get(col, ""))
        if n is not None:
            r[col] = n


def _group_sum(records: list[dict[str, Any]], group: str, value: str) -> list[dict[str, Any]]:
    bucket: dict[str, float] = defaultdict(float)
    for r in records:
        v = _to_num(str(r.get(value, "")))
        if v is None:
            continue
        bucket[str(r.get(group, ""))] += v
    return [{group: k, value: v} for k, v in sorted(bucket.items(), key=lambda kv: -kv[1])]


def _group_count(records: list[dict[str, Any]], group: str) -> list[dict[str, Any]]:
    c = Counter(str(r.get(group, "")) for r in records)
    return [{group: k, "count": n} for k, n in c.most_common()]


# ─── Spec builders ───────────────────────────────────────────────────────

def _base(title: str, data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "data": {"values": data},
        "width": "container",
        "height": 280,
        "config": {
            "view": {"stroke": "transparent"},
            "axis": {"labelFontSize": 11, "titleFontSize": 12, "domainColor": "#0a0a0a"},
            "title": {"fontSize": 14, "fontWeight": 600, "anchor": "start"},
        },
    }


def build_bar(records: list[dict[str, Any]], x: str, y: str | None, agg: str = "sum") -> dict[str, Any]:
    if y is None:
        data = _group_count(records, x)
        spec = _base(f"Count of {x}", data)
        spec["mark"] = {"type": "bar", "color": "#F5C26B"}
        spec["encoding"] = {
            "x": {"field": x, "type": "nominal", "sort": "-y"},
            "y": {"field": "count", "type": "quantitative", "title": "count"},
        }
    else:
        data = _group_sum(records, x, y)
        spec = _base(f"{agg.title()} of {y} by {x}", data)
        spec["mark"] = {"type": "bar", "color": "#F5C26B"}
        spec["encoding"] = {
            "x": {"field": x, "type": "nominal", "sort": "-y"},
            "y": {"field": y, "type": "quantitative", "aggregate": None},
        }
    return spec


def build_line(records: list[dict[str, Any]], x: str, y: str) -> dict[str, Any]:
    _coerce_num(records, y)
    spec = _base(f"{y} over {x}", records)
    spec["mark"] = {"type": "line", "color": "#0a0a0a", "point": {"color": "#F58A6B"}}
    spec["encoding"] = {
        "x": {"field": x, "type": "temporal"},
        "y": {"field": y, "type": "quantitative"},
    }
    return spec


def build_area(records: list[dict[str, Any]], x: str, y: str) -> dict[str, Any]:
    spec = build_line(records, x, y)
    spec["mark"] = {"type": "area", "color": "#A7E3B8", "line": {"color": "#0a0a0a"}, "opacity": 0.7}
    spec["title"] = f"{y} cumulative area over {x}"
    return spec


def build_scatter(records: list[dict[str, Any]], x: str, y: str, color: str | None = None) -> dict[str, Any]:
    _coerce_num(records, x)
    _coerce_num(records, y)
    spec = _base(f"{y} vs {x}", records)
    spec["mark"] = {"type": "point", "filled": True, "color": "#F58A6B", "opacity": 0.7, "size": 60}
    spec["encoding"] = {
        "x": {"field": x, "type": "quantitative"},
        "y": {"field": y, "type": "quantitative"},
    }
    if color:
        spec["encoding"]["color"] = {"field": color, "type": "nominal"}
    return spec


def build_hist(records: list[dict[str, Any]], x: str, bins: int = 20) -> dict[str, Any]:
    _coerce_num(records, x)
    spec = _base(f"Distribution of {x}", records)
    spec["mark"] = {"type": "bar", "color": "#A7E3B8"}
    spec["encoding"] = {
        "x": {"field": x, "type": "quantitative", "bin": {"maxbins": bins}},
        "y": {"aggregate": "count", "type": "quantitative"},
    }
    return spec


def build_pie(records: list[dict[str, Any]], group: str, value: str | None = None) -> dict[str, Any]:
    data = _group_sum(records, group, value) if value else _group_count(records, group)
    metric = value or "count"
    spec = _base(f"Share of {metric} by {group}", data)
    spec["mark"] = {"type": "arc", "innerRadius": 50}
    spec["encoding"] = {
        "theta": {"field": metric, "type": "quantitative"},
        "color": {"field": group, "type": "nominal"},
    }
    spec.pop("height", None)
    spec["height"] = 280
    return spec


def build_heatmap(records: list[dict[str, Any]], x: str, y: str, value: str | None = None) -> dict[str, Any]:
    spec = _base(f"Heatmap: {y} × {x}", records)
    spec["mark"] = {"type": "rect"}
    spec["encoding"] = {
        "x": {"field": x, "type": "nominal"},
        "y": {"field": y, "type": "nominal"},
        "color": {
            "field": value if value else "*",
            "type": "quantitative",
            "aggregate": "sum" if value else "count",
            "scale": {"scheme": "yelloworangered"},
        },
    }
    return spec


KINDS = {
    "bar": build_bar,
    "line": build_line,
    "area": build_area,
    "scatter": build_scatter,
    "hist": build_hist,
    "pie": build_pie,
    "heatmap": build_heatmap,
}


# ─── Suggestion engine ───────────────────────────────────────────────────

def suggest_charts(profile: list[dict[str, Any]]) -> list[dict[str, Any]]:
    num_cols = [c["name"] for c in profile if c["type"] == "number"]
    cat_cols = [c["name"] for c in profile if c["type"] == "string" and 2 <= c["unique"] <= 25]
    date_cols = [c["name"] for c in profile if c["type"] == "date"]

    ideas: list[dict[str, Any]] = []

    for d in date_cols:
        for n in num_cols[:3]:
            ideas.append({
                "kind": "line",
                "title": f"{n} over time ({d})",
                "args": {"x": d, "y": n},
                "rationale": "Time-series trend reveals seasonality + level shifts.",
            })

    for cat in cat_cols[:3]:
        for n in num_cols[:2]:
            ideas.append({
                "kind": "bar",
                "title": f"Total {n} by {cat}",
                "args": {"x": cat, "y": n},
                "rationale": "Compare contribution of categories on the key metric.",
            })
        ideas.append({
            "kind": "pie",
            "title": f"Share of records by {cat}",
            "args": {"group": cat},
            "rationale": "Show distribution of records across categories.",
        })

    for n in num_cols[:3]:
        ideas.append({
            "kind": "hist",
            "title": f"Distribution of {n}",
            "args": {"x": n},
            "rationale": "Spot skew, modes, and outliers.",
        })

    if len(num_cols) >= 2:
        ideas.append({
            "kind": "scatter",
            "title": f"{num_cols[1]} vs {num_cols[0]}",
            "args": {"x": num_cols[0], "y": num_cols[1], "color": cat_cols[0] if cat_cols else None},
            "rationale": "Investigate correlation between the two main metrics.",
        })

    if len(cat_cols) >= 2:
        ideas.append({
            "kind": "heatmap",
            "title": f"Heatmap of records: {cat_cols[1]} × {cat_cols[0]}",
            "args": {"x": cat_cols[0], "y": cat_cols[1]},
            "rationale": "Surface dense combinations of two categorical dimensions.",
        })

    return ideas


# ─── CLI ─────────────────────────────────────────────────────────────────

def cmd_suggest(args: argparse.Namespace) -> int:
    header, rows, path = load(args.path, sheet=args.sheet)
    cols = profile_columns(header, rows)
    ideas = suggest_charts(cols)
    out = {"path": str(path), "rows": len(rows), "ideas": ideas}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_spec(args: argparse.Namespace) -> int:
    header, rows, path = load(args.path, sheet=args.sheet)
    records = _rows_to_records(header, rows)
    if args.kind not in KINDS:
        print(f"ERROR: unknown chart kind: {args.kind}. choices: {sorted(KINDS)}", file=sys.stderr)
        return 2

    builder = KINDS[args.kind]
    kwargs: dict[str, Any] = {}
    if args.kind == "bar":
        kwargs = {"x": args.x, "y": args.y}
    elif args.kind in ("line", "area"):
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

    out = {
        "path": str(path),
        "kind": args.kind,
        "title": args.title or spec.get("title", args.kind),
        "spec": spec,
        "vega_lib": VEGA_LIB_URL,
    }
    if args.save:
        save_path = Path(args.save).expanduser()
        if not save_path.is_absolute():
            save_path = ROOT / "data" / "charts" / save_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        # CRITICAL: only print a short receipt — never echo the spec to stdout.
        # Embedded `data.values` arrays are the #1 cause of context-window blowups.
        n_rows = len(spec.get("data", {}).get("values", []))
        print(json.dumps({"saved": str(save_path), "kind": args.kind, "rows_embedded": n_rows}, ensure_ascii=False))
    else:
        # Stdout-only mode: strip embedded data so the model never reads thousands
        # of values. Pass --save to materialise the full, renderable spec.
        compact = dict(out)
        compact["spec"] = {k: v for k, v in spec.items() if k != "data"}
        compact["spec"]["data"] = {"values": "<<elided — use --save to write full spec>>"}
        compact["rows_elided"] = len(spec.get("data", {}).get("values", []))
        print(json.dumps(compact, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Vega-Lite chart spec builder.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def _add_io(p: argparse.ArgumentParser) -> None:
        p.add_argument("--path", required=True)
        p.add_argument("--sheet")

    p_sug = sub.add_parser("suggest", help="propose chart ideas based on data profile")
    _add_io(p_sug)
    p_sug.set_defaults(fn=cmd_suggest)

    p_spec = sub.add_parser("spec", help="build a single chart spec")
    _add_io(p_spec)
    p_spec.add_argument("--kind", required=True, choices=sorted(KINDS))
    p_spec.add_argument("--x", help="x / group / dimension field")
    p_spec.add_argument("--y", help="y / metric field")
    p_spec.add_argument("--color", help="optional color field (scatter, heatmap value)")
    p_spec.add_argument("--bins", type=int, default=20)
    p_spec.add_argument("--title", help="override chart title")
    p_spec.add_argument("--save", help="save spec to this path (relative paths land under data/charts/)")
    p_spec.set_defaults(fn=cmd_spec)

    args = parser.parse_args(argv[1:])
    if getattr(args, "sheet", None) and args.sheet.isdigit():
        args.sheet = int(args.sheet)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
