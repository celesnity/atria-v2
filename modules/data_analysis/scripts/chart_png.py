#!/usr/bin/env python
"""Render a chart to PNG via matplotlib AND register it in the project.

Why this exists alongside `chart.py` / `viz_agent.py`:
  * Vega-Lite specs (the existing flow) render perfectly in the dashboard
    and the PDF report, but the *chat stream* needs an inline preview the
    agent can hand back to the user in the same turn as the SQL.
  * Headless PNG is the cheapest way to get a previewable image into a
    markdown chat message (`![chart](data:image/png;base64,...)`). The
    LLM can drop the data URI straight into its reply alongside the SQL
    block — one round-trip, no iframe required.

Pipeline:
  SQL → DuckDB (warehouse + parquet views) → rows → matplotlib → PNG file
       → register chart record (with png_path) → echo {chart_id, png_path,
         data_uri, kind, rows} as JSON.

The chart record uses the SAME schema as `chart.py spec --save` so the
existing `pin` + `report` flow picks it up without modification. The PDF
report renderer falls back to PNG when `png_path` is present.

Allowed kinds: bar | line | scatter | hist | pie.

Usage:
  da scripts/chart_png.py create \\
      --slug s1 --kind bar --x category --y total \\
      --title "Sales by region" \\
      --sql "SELECT category, SUM(amount) AS total FROM \\"sales\\" GROUP BY 1"
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import duck, workspace as ws  # noqa: E402


def _resolve_sql(arg: str) -> str:
    if arg.startswith("@"):
        return Path(arg[1:]).expanduser().read_text(encoding="utf-8")
    return arg


def _views_for(slug: str) -> dict[str, Path]:
    """Map view-name → parquet for every registered dataset (sheet-aware)."""
    return {(d.get("table") or d["name"]): Path(d["parquet"]) for d in ws.list_datasets(slug)}


def _render(kind: str, rows: list[list], columns: list[str], *, x: str, y: str | None,
            title: str, width: float, height: float, dpi: int) -> bytes:
    """Build the PNG body. Matplotlib is imported lazily — first call is slow
    but subsequent calls in the same process reuse the cache.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        ix = columns.index(x)
    except ValueError:
        raise SystemExit(f"ERROR: x column '{x}' not in result columns: {columns}")
    iy: int | None = None
    if y is not None:
        try:
            iy = columns.index(y)
        except ValueError:
            raise SystemExit(f"ERROR: y column '{y}' not in result columns: {columns}")

    xs = [r[ix] for r in rows]
    ys = [r[iy] for r in rows] if iy is not None else None

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.set_title(title)

    if kind == "bar":
        if ys is None:
            raise SystemExit("ERROR: --y required for bar")
        ax.bar([str(v) for v in xs], [_to_float(v) for v in ys])
        ax.tick_params(axis="x", rotation=30)
    elif kind == "line":
        if ys is None:
            raise SystemExit("ERROR: --y required for line")
        ax.plot(xs, [_to_float(v) for v in ys], marker="o")
        ax.tick_params(axis="x", rotation=30)
    elif kind == "scatter":
        if ys is None:
            raise SystemExit("ERROR: --y required for scatter")
        ax.scatter([_to_float(v) for v in xs], [_to_float(v) for v in ys], alpha=0.6)
    elif kind == "hist":
        ax.hist([_to_float(v) for v in xs if v is not None], bins=20)
    elif kind == "pie":
        if ys is None:
            raise SystemExit("ERROR: --y required for pie")
        ax.pie([_to_float(v) for v in ys], labels=[str(v) for v in xs],
               autopct="%1.1f%%", startangle=90)
        ax.set_ylabel("")
    else:
        raise SystemExit(f"ERROR: unsupported kind: {kind}")

    ax.set_xlabel(x)
    if y:
        ax.set_ylabel(y)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _to_float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def cmd_create(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    dirs = ws.ensure_project_dirs(args.slug)
    sql = _resolve_sql(args.sql)
    views = _views_for(args.slug)
    result = duck.execute_sql(sql, views)
    if not result["rows"]:
        print("ERROR: SQL returned 0 rows", file=sys.stderr)
        return 1

    png_bytes = _render(
        args.kind, result["rows"], result["columns"],
        x=args.x, y=args.y, title=args.title or args.kind,
        width=args.width, height=args.height, dpi=args.dpi,
    )

    chart_id = ws.new_id("ch_")
    png_dir = dirs["charts"] / "png"
    png_dir.mkdir(parents=True, exist_ok=True)
    png_path = png_dir / f"{chart_id}.png"
    png_path.write_bytes(png_bytes)

    # Minimal spec retained so the dashboard + Vega-based renderers also work.
    # Spec encodes intent (kind/x/y); PNG is the truth for inline + PDF.
    spec_stub = {
        "kind": args.kind, "x": args.x, "y": args.y,
        "rendered_by": "matplotlib", "png_path": str(png_path),
    }

    meta = {
        "id": chart_id,
        "project": args.slug,
        "title": args.title or args.kind,
        "kind": args.kind,
        "sql": sql,
        "spec": spec_stub,
        "png_path": str(png_path),
        "created_at": ws.now(),
        "rows_used": len(result["rows"]),
        "columns_used": result["columns"],
    }
    ws.save_chart(args.slug, meta)

    if args.embed_data_uri:
        data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    else:
        data_uri = None

    out = {
        "chart_id": chart_id,
        "png_path": str(png_path),
        "kind": args.kind,
        "rows": len(result["rows"]),
        "title": meta["title"],
        "sql": sql,
        "data_uri": data_uri,
        "data_uri_size": len(data_uri) if data_uri else 0,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Matplotlib chart → PNG → register.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("create", help="run SQL → matplotlib → PNG → register chart")
    pc.add_argument("--slug", required=True)
    pc.add_argument("--kind", required=True, choices=("bar", "line", "scatter", "hist", "pie"))
    pc.add_argument("--sql", required=True, help="SQL string (or @path/to.sql)")
    pc.add_argument("--x", required=True)
    pc.add_argument("--y", help="omit only for hist (single-axis)")
    pc.add_argument("--title")
    pc.add_argument("--width", type=float, default=6.4)
    pc.add_argument("--height", type=float, default=4.0)
    pc.add_argument("--dpi", type=int, default=120)
    pc.add_argument("--embed-data-uri", dest="embed_data_uri", action="store_true",
                    help="also emit a base64 data URI in the JSON output "
                         "(use this when the LLM will drop it straight into a chat message)")
    pc.set_defaults(fn=cmd_create)

    args = p.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
