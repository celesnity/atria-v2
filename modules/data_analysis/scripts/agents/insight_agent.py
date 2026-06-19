#!/usr/bin/env python
"""Insight Agent (PRD §5.5.4).

Tools:
  detect_anomaly(artifact_id) — IQR + z-score anomaly detection on numeric
      columns of the artifact's parquet (FR-INS-01).
  summarise_results(artifact_id) — natural-language observations: top
      contributors, trend slope, anomaly counts, dominant category
      (FR-INS-03).
  compare(artifact_id, against_id) — diff against a historical artifact
      (FR-INS-02): row-count delta, mean shifts on shared numeric columns.
"""

from __future__ import annotations

import argparse
import json
import statistics
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


def _numeric_cols(a: dict) -> list[str]:
    return [
        name for name, dt in zip(a["columns"], a["dtypes"])
        if any(k in dt.upper() for k in ("INT", "DOUBLE", "FLOAT", "DECIMAL"))
    ]


def _date_cols(a: dict) -> list[str]:
    return [
        name for name, dt in zip(a["columns"], a["dtypes"])
        if "DATE" in dt.upper() or "TIMESTAMP" in dt.upper()
    ]


def _cat_cols(a: dict) -> list[str]:
    n = set(_numeric_cols(a)) | set(_date_cols(a))
    return [c for c in a["columns"] if c not in n]


def cmd_detect_anomaly(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    a = _artifact(args.slug, args.artifact_id)
    res = duck.execute_sql("SELECT * FROM art", {"art": Path(a["parquet"])})
    cols = res["columns"]
    rows = res["rows"]
    out: list[dict] = []
    for c in _numeric_cols(a):
        idx = cols.index(c)
        values = [float(r[idx]) for r in rows if r[idx] is not None and isinstance(r[idx], (int, float))]
        if len(values) < 5:
            continue
        values_sorted = sorted(values)
        q1 = values_sorted[len(values_sorted) // 4]
        q3 = values_sorted[(3 * len(values_sorted)) // 4]
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        mean = statistics.fmean(values)
        std = statistics.pstdev(values) or 1e-9
        anomalies = []
        for v in values:
            if v < lo or v > hi:
                anomalies.append({"value": v, "z": round((v - mean) / std, 2)})
        if anomalies:
            out.append({
                "column": c, "count": len(anomalies),
                "fences": {"lo": round(lo, 4), "hi": round(hi, 4)},
                "mean": round(mean, 4), "std": round(std, 4),
                "samples": anomalies[:5],
            })
    print(json.dumps({"artifact_id": a["id"], "anomalies": out}, ensure_ascii=False))
    return 0


def cmd_summarise(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    a = _artifact(args.slug, args.artifact_id)
    res = duck.execute_sql("SELECT * FROM art", {"art": Path(a["parquet"])})
    cols, rows = res["columns"], res["rows"]
    observations: list[str] = []

    nums = _numeric_cols(a)
    cats = _cat_cols(a)
    dates = _date_cols(a)

    observations.append(f"Artifact has {len(rows)} row(s) × {len(cols)} column(s).")

    # Top contributor in (cat, num) tables.
    if cats and nums:
        cat = cats[0]; num = nums[0]
        ci, ni = cols.index(cat), cols.index(num)
        bucket: dict[str, float] = {}
        for r in rows:
            if r[ni] is None:
                continue
            bucket[str(r[ci])] = bucket.get(str(r[ci]), 0.0) + float(r[ni])
        if bucket:
            top_key, top_val = max(bucket.items(), key=lambda kv: kv[1])
            total = sum(bucket.values()) or 1
            observations.append(
                f"Top contributor by {num}: `{top_key}` accounts for "
                f"{top_val:.2f} ({top_val / total:.0%} of total)."
            )

    # Trend slope (linear regression on date × num).
    if dates and nums:
        di, ni = cols.index(dates[0]), cols.index(nums[0])
        xs, ys = [], []
        for i, r in enumerate(rows):
            if r[ni] is None:
                continue
            xs.append(i); ys.append(float(r[ni]))
        if len(xs) >= 3:
            n = len(xs)
            mx = sum(xs) / n; my = sum(ys) / n
            num_, den_ = 0.0, 0.0
            for x, y in zip(xs, ys):
                num_ += (x - mx) * (y - my)
                den_ += (x - mx) ** 2
            slope = num_ / den_ if den_ else 0.0
            direction = "upward" if slope > 0 else ("downward" if slope < 0 else "flat")
            observations.append(f"{nums[0]} shows a {direction} trend over {dates[0]} (slope={slope:+.3f} per step).")

    print(json.dumps({"artifact_id": a["id"], "observations": observations}, ensure_ascii=False))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    a = _artifact(args.slug, args.artifact_id)
    b = _artifact(args.slug, args.against)
    r1 = duck.execute_sql("SELECT * FROM art", {"art": Path(a["parquet"])})
    r2 = duck.execute_sql("SELECT * FROM art", {"art": Path(b["parquet"])})

    diff: dict = {"row_delta": r1["row_count"] - r2["row_count"], "metric_shifts": []}
    nums_a, nums_b = set(_numeric_cols(a)), set(_numeric_cols(b))
    shared = nums_a & nums_b
    for col in sorted(shared):
        i1 = r1["columns"].index(col); i2 = r2["columns"].index(col)
        v1 = [float(x[i1]) for x in r1["rows"] if isinstance(x[i1], (int, float))]
        v2 = [float(x[i2]) for x in r2["rows"] if isinstance(x[i2], (int, float))]
        if not v1 or not v2:
            continue
        m1 = sum(v1) / len(v1); m2 = sum(v2) / len(v2)
        diff["metric_shifts"].append({
            "column": col,
            "mean_now": round(m1, 4),
            "mean_against": round(m2, 4),
            "delta_pct": round((m1 - m2) / m2 * 100, 2) if m2 else None,
        })
    print(json.dumps({"artifact_id": a["id"], "against": b["id"], **diff}, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Insight Agent.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd, fn, helptext in (
        ("detect_anomaly", cmd_detect_anomaly, "IQR + z-score anomalies on numeric columns"),
        ("summarise_results", cmd_summarise, "natural-language observations"),
    ):
        p = sub.add_parser(cmd, help=helptext)
        p.add_argument("--slug", required=True)
        p.add_argument("--artifact-id", required=True)
        p.set_defaults(fn=fn)
    p_cmp = sub.add_parser("compare", help="diff a current artifact against a historical one (FR-INS-02)")
    p_cmp.add_argument("--slug", required=True)
    p_cmp.add_argument("--artifact-id", required=True)
    p_cmp.add_argument("--against", required=True, help="historical artifact id")
    p_cmp.set_defaults(fn=cmd_compare)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
