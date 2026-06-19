#!/usr/bin/env python
"""Dataset ingest + management (FR-DS-*) and the Data Agent's tools.

Subcommands:
  ingest          — upload CSV/XLSX → convert to Parquet, profile, persist metadata
  list            — list datasets in a project
  schema          — print schema + column profile of a dataset
  relationships   — discover cross-dataset join candidates with confidence scores
  read_dataset    — tool surface: stream first N rows of a dataset's Parquet
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import duck, workspace as ws  # noqa: E402
from core.relationships import discover  # noqa: E402


def _ingest_one(
    slug: str,
    proj: dict,
    dirs: dict,
    src: Path,
    raw_copy: Path,
    base_name: str,
    sheet: str | int | None,
    sheet_label: str | None,
    tags: list[str],
) -> dict:
    """Ingest a single tabular source (or one sheet of an xlsx) → dataset meta."""
    dataset_id = ws.new_id("ds_")
    parquet_path = dirs["datasets"] / f"{dataset_id}.parquet"
    info = duck.ingest(src, parquet_path, sheet=sheet)
    profile = duck.profile_parquet(parquet_path)

    name = f"{base_name} · {sheet_label}" if sheet_label else base_name
    table_name = ws.slugify(name).replace("-", "_") or dataset_id

    meta = {
        "id": dataset_id,
        "project": proj["slug"],
        "name": name,
        "source_filename": src.name,
        "raw_path": str(raw_copy),
        "parquet": str(parquet_path),
        "sheet": sheet_label,
        "table": table_name,
        "rows": info["rows"],
        "columns": profile["columns"],
        "ingested_at": ws.now(),
        "tags": tags,
    }
    ws.save_dataset(slug, meta)

    # Register as a persistent table in the project's warehouse.duckdb so it
    # survives across sessions and is queryable without re-registering views.
    try:
        duck.register_parquet_table(ws.warehouse_path(slug), table_name, parquet_path)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — warehouse is best-effort
        print(f"WARN: warehouse register failed for {table_name}: {exc}", file=sys.stderr)

    return meta


def cmd_ingest(args: argparse.Namespace) -> int:
    proj = ws.require_project(args.slug)
    src = Path(args.path).expanduser()
    if not src.exists():
        print(f"ERROR: file not found: {src}", file=sys.stderr)
        return 1

    dirs = ws.ensure_project_dirs(args.slug)
    base_name = args.name or src.stem
    tags = args.tag or []

    # Keep the raw upload once; all per-sheet datasets share it.
    raw_id = ws.new_id("raw_")
    raw_copy = dirs["datasets_raw"] / f"{raw_id}{src.suffix}"
    shutil.copy(src, raw_copy)

    is_excel = src.suffix.lower() in (".xlsx", ".xlsm", ".xls")
    metas: list[dict] = []

    if is_excel and args.sheet is None:
        # Multi-sheet auto-expand: one dataset per sheet.
        sheets = duck.xlsx_list_sheets(src)
        if not sheets:
            print("ERROR: workbook has no sheets", file=sys.stderr)
            return 1
        for sheet_name in sheets:
            try:
                metas.append(
                    _ingest_one(
                        args.slug, proj, dirs, src, raw_copy,
                        base_name, sheet=sheet_name, sheet_label=sheet_name, tags=tags,
                    )
                )
            except SystemExit as exc:
                # Empty / unreadable sheet — skip but keep going.
                print(f"WARN: skipped sheet '{sheet_name}': {exc}", file=sys.stderr)
    else:
        # CSV/TSV, or xlsx with explicit --sheet → single dataset.
        sheet_label = str(args.sheet) if (is_excel and args.sheet is not None) else None
        metas.append(
            _ingest_one(
                args.slug, proj, dirs, src, raw_copy,
                base_name, sheet=args.sheet, sheet_label=sheet_label, tags=tags,
            )
        )

    if not metas:
        print("ERROR: no datasets ingested", file=sys.stderr)
        return 1

    total_rows = sum(m["rows"] for m in metas)
    print(f"ingested {len(metas)} dataset(s) · {total_rows:,} rows total")
    for m in metas:
        suffix = f" [{m['sheet']}]" if m.get("sheet") else ""
        print(f"  {m['id']}  {m['name']}{suffix}  →  table \"{m['table']}\"  ({m['rows']:,} rows)")
    if args.json:
        print(json.dumps(metas if len(metas) > 1 else metas[0], ensure_ascii=False))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    datasets = ws.list_datasets(args.slug)
    if args.json:
        print(json.dumps(datasets, ensure_ascii=False))
        return 0
    if not datasets:
        print("(no datasets)")
        return 0
    for d in datasets:
        print(f"  [{d['id'][:10]}] {d['name']:<30}  {d['rows']:>8,} rows  {len(d.get('columns', []))} cols")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    d = ws.get_dataset(args.slug, args.id)
    if not d:
        # Allow id-prefix.
        for cand in ws.list_datasets(args.slug):
            if cand["id"].startswith(args.id):
                d = cand
                break
    if not d:
        print(f"ERROR: dataset not found: {args.id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(d, ensure_ascii=False))
        return 0
    print(f"dataset: {d['name']}  ({d['id']})")
    print(f"parquet: {d['parquet']}")
    print(f"rows:    {d['rows']:,}")
    for c in d.get("columns", []):
        line = f"  {c['name']:<28} {c['type']:<14} nulls={c['null']:<5} unique={c['unique']}"
        if c.get("stats"):
            s = c["stats"]
            line += f"  μ={s.get('mean')}  [{s.get('min')} .. {s.get('max')}]"
        print(line)
    return 0


def cmd_relationships(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    datasets = ws.list_datasets(args.slug)
    if len(datasets) < 2:
        print("(need ≥ 2 datasets for relationship discovery)")
        return 0
    candidates = discover(datasets)
    out = {"candidates": candidates}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
        return 0
    if not candidates:
        print("(no candidate join keys found)")
        return 0
    for c in candidates:
        print(f"  [{c['decision']:<7}] {c['score']:.2f}  "
              f"{c['left']['name']}.{c['left']['column']}  ↔  "
              f"{c['right']['name']}.{c['right']['column']}  "
              f"(name {c['name_sim']:.2f} · type {c['type_compat']:.2f} · overlap {c['value_overlap']:.2f})")
    return 0


def cmd_read_dataset(args: argparse.Namespace) -> int:
    """Tool surface: read_dataset(project, id, limit) (PRD §9).

    Defaults to a TINY preview (10 rows) — the model should NEVER need
    to materialise the full dataset; that's what SQL is for. Pass --limit
    explicitly when more rows are genuinely needed.
    """
    ws.require_project(args.slug)
    d = ws.get_dataset(args.slug, args.id) or next(
        (x for x in ws.list_datasets(args.slug) if x["id"].startswith(args.id)), None
    )
    if not d:
        print(f"ERROR: dataset not found: {args.id}", file=sys.stderr)
        return 1
    limit = min(int(args.limit), 100)  # hard ceiling, regardless of caller
    result = duck.execute_sql(f"SELECT * FROM ds LIMIT {limit}", {"ds": Path(d["parquet"])})
    out = {
        "dataset_id": d["id"], "name": d["name"], "total_rows": d.get("rows"),
        "columns": result["columns"], "rows": result["rows"],
        "preview_limit": limit,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_anomalies(args: argparse.Namespace) -> int:
    """Time-series anomaly scan on a registered dataset.

    Flags three classes against the (time-ordered) ``--value`` column:
      * outlier   — |rolling z-score| ≥ --z (window = --window)
      * spike     — |Δ vs previous| / |previous| ≥ --ratio
      * step      — |mean(after) − mean(before)| / pooled_std ≥ --step-z,
                    using a symmetric --step-window on each side.

    Implementation rides DuckDB window functions on the dataset's Parquet —
    O(N) single-pass, no Python-side accumulation.
    """
    ws.require_project(args.slug)
    d = ws.get_dataset(args.slug, args.id) or next(
        (x for x in ws.list_datasets(args.slug) if x["id"].startswith(args.id)), None
    )
    if not d:
        print(f"ERROR: dataset not found: {args.id}", file=sys.stderr)
        return 1

    parquet = str(Path(d["parquet"])).replace("'", "''")
    time_col = args.time.replace('"', '""')
    value_col = args.value.replace('"', '""')
    w = max(int(args.window), 2)
    sw = max(int(args.step_window), 2)

    sql = f"""
    WITH src AS (
      SELECT "{time_col}" AS ts,
             CAST("{value_col}" AS DOUBLE) AS val
      FROM read_parquet('{parquet}')
      WHERE "{value_col}" IS NOT NULL AND "{time_col}" IS NOT NULL
    ),
    ord AS (
      SELECT ts, val, ROW_NUMBER() OVER (ORDER BY ts) AS rn FROM src
    )
    SELECT
      ts, val, rn,
      AVG(val)         OVER (ORDER BY rn ROWS BETWEEN {w} PRECEDING AND 1 PRECEDING) AS m_pre,
      STDDEV_SAMP(val) OVER (ORDER BY rn ROWS BETWEEN {w} PRECEDING AND 1 PRECEDING) AS s_pre,
      LAG(val, 1)      OVER (ORDER BY rn) AS prev_val,
      AVG(val)         OVER (ORDER BY rn ROWS BETWEEN {sw} PRECEDING AND 1 PRECEDING) AS m_before,
      STDDEV_SAMP(val) OVER (ORDER BY rn ROWS BETWEEN {sw} PRECEDING AND 1 PRECEDING) AS s_before,
      AVG(val)         OVER (ORDER BY rn ROWS BETWEEN CURRENT ROW AND {sw - 1} FOLLOWING) AS m_after,
      STDDEV_SAMP(val) OVER (ORDER BY rn ROWS BETWEEN CURRENT ROW AND {sw - 1} FOLLOWING) AS s_after
    FROM ord
    ORDER BY rn
    """
    result = duck.execute_sql(sql, {})  # no view substitutions — query is self-contained

    anomalies: list[dict] = []
    for row in result["rows"]:
        ts, val, _rn, m_pre, s_pre, prev_val, m_b, s_b, m_a, s_a = row
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue

        # Rolling outlier
        if m_pre is not None and s_pre and s_pre > 0:
            z = (v - m_pre) / s_pre
            if abs(z) >= args.z:
                anomalies.append({
                    "kind": "outlier", "ts": str(ts), "value": v,
                    "z_score": round(z, 3), "baseline_mean": round(m_pre, 4),
                })
        # Ratio spike vs previous point
        if prev_val is not None:
            try:
                pv = float(prev_val)
                if pv != 0:
                    r = (v - pv) / abs(pv)
                    if abs(r) >= args.ratio:
                        anomalies.append({
                            "kind": "spike", "ts": str(ts), "value": v,
                            "prev_value": pv, "ratio_delta": round(r, 3),
                        })
            except (TypeError, ValueError):
                pass
        # Step change — two-window mean diff over pooled std
        if m_b is not None and m_a is not None:
            pooled = ((s_b or 0.0) ** 2 + (s_a or 0.0) ** 2) ** 0.5
            if pooled > 0:
                step = (m_a - m_b) / pooled
                if abs(step) >= args.step_z:
                    anomalies.append({
                        "kind": "step", "ts": str(ts),
                        "mean_before": round(m_b, 4), "mean_after": round(m_a, 4),
                        "step_z": round(step, 3),
                    })

    # Cap output: keep highest-magnitude per kind to stay token-cheap.
    def _mag(a: dict) -> float:
        return abs(a.get("z_score") or a.get("ratio_delta") or a.get("step_z") or 0)
    anomalies.sort(key=_mag, reverse=True)
    cap = max(int(args.limit), 1)
    anomalies = anomalies[:cap]

    out = {
        "dataset_id": d["id"],
        "time_col": args.time, "value_col": args.value,
        "params": {"window": w, "z": args.z, "ratio": args.ratio,
                   "step_window": sw, "step_z": args.step_z},
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Dataset ingest + Data Agent surface.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="upload CSV/XLSX → Parquet + profile (FR-DS-01..05)")
    p_ing.add_argument("--slug", required=True)
    p_ing.add_argument("--path", required=True)
    p_ing.add_argument("--name", help="display name (defaults to filename stem)")
    p_ing.add_argument("--sheet", help="Excel sheet name or 0-based index")
    p_ing.add_argument("--tag", action="append", help="tag (repeatable)")
    p_ing.add_argument("--json", action="store_true")
    p_ing.set_defaults(fn=cmd_ingest)

    p_ls = sub.add_parser("list", help="list datasets in a project")
    p_ls.add_argument("--slug", required=True)
    p_ls.add_argument("--json", action="store_true")
    p_ls.set_defaults(fn=cmd_list)

    p_sc = sub.add_parser("schema", help="show a dataset schema + profile")
    p_sc.add_argument("--slug", required=True)
    p_sc.add_argument("--id", required=True, help="dataset id or id prefix")
    p_sc.add_argument("--json", action="store_true")
    p_sc.set_defaults(fn=cmd_schema)

    p_rel = sub.add_parser("relationships", help="discover cross-dataset joins with confidence (FR-DATA-04)")
    p_rel.add_argument("--slug", required=True)
    p_rel.add_argument("--json", action="store_true")
    p_rel.set_defaults(fn=cmd_relationships)

    p_rd = sub.add_parser("read_dataset", help="tool: stream first N rows as JSON")
    p_rd.add_argument("--slug", required=True)
    p_rd.add_argument("--id", required=True)
    p_rd.add_argument("--limit", type=int, default=10, help="row cap (hard ceiling 100, default 10)")
    p_rd.set_defaults(fn=cmd_read_dataset)

    p_an = sub.add_parser("anomalies", help="rolling-z outliers, ratio spikes, step changes on a time-ordered metric")
    p_an.add_argument("--slug", required=True)
    p_an.add_argument("--id", required=True, help="dataset id or id prefix")
    p_an.add_argument("--time", required=True, help="time/order column name")
    p_an.add_argument("--value", required=True, help="numeric column to scan")
    p_an.add_argument("--window", type=int, default=20, help="rolling window for z-score baseline (default 20)")
    p_an.add_argument("--z", type=float, default=3.0, help="|z| threshold to flag an outlier (default 3.0)")
    p_an.add_argument("--ratio", type=float, default=0.5, help="|Δ/prev| threshold for a spike (default 0.5 = 50%%)")
    p_an.add_argument("--step-window", dest="step_window", type=int, default=10, help="symmetric window for step-change scan")
    p_an.add_argument("--step-z", dest="step_z", type=float, default=3.0, help="(mean_after − mean_before)/pooled_std threshold")
    p_an.add_argument("--limit", type=int, default=50, help="max anomalies returned (sorted by magnitude)")
    p_an.set_defaults(fn=cmd_anomalies)

    args = parser.parse_args(argv[1:])
    if getattr(args, "sheet", None) and args.sheet and args.sheet.isdigit():
        args.sheet = int(args.sheet)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
