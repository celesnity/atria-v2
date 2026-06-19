#!/usr/bin/env python
"""Agentic surface for the data_analysis module.

Goal: collapse the deterministic choreography (ingest → profile → ideas → SQL →
chart → save → trace) into a handful of high-level *intents* the host LLM can
call directly. Every command emits compact JSON so the LLM stays in control
without having to plan five tool calls per turn.

Subcommands:
  onboard  — create project (if needed) + ingest file + profile + seed brief
  brief    — one-shot project context dump (datasets + schemas + recent work)
  scan     — auto-anomaly sweep across (date × numeric) pairs of a dataset
  recall   — answer-from-memory: top-k matching prior artifacts for a question
  next     — propose 3-5 next analysis steps based on current project state
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import duck, workspace as ws  # noqa: E402
from core.retrieve import retrieve  # noqa: E402


# ─── small helpers ─────────────────────────────────────────────────────────

def _resolve_chat_id(explicit: str | None) -> str | None:
    return explicit or os.environ.get("ATRIA_SESSION_ID") or os.environ.get("ATRIA_CONVERSATION_ID")


def _emit(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, default=str))


def _schema_brief(d: dict) -> dict:
    """Compress a dataset metadata blob to what the LLM actually needs."""
    cols = []
    for c in d.get("columns", []):
        item: dict[str, Any] = {"name": c["name"], "type": c["type"], "null": c["null"], "unique": c["unique"]}
        if c.get("stats"):
            s = c["stats"]
            item["range"] = [s.get("min"), s.get("max")]
            item["mean"] = s.get("mean")
        if c.get("top_values"):
            item["sample_values"] = [t["value"] for t in c["top_values"][:3]]
        cols.append(item)
    return {
        "id": d["id"], "name": d["name"], "table": d.get("table"),
        "sheet": d.get("sheet"), "rows": d["rows"], "columns": cols,
    }


def _classify_columns(profile: list[dict]) -> dict[str, list[str]]:
    nums: list[str] = []
    dates: list[str] = []
    cats: list[str] = []
    for c in profile:
        t = (c.get("type") or "").lower()
        if t in ("number",) or "double" in t or "int" in t or "decimal" in t or "float" in t:
            nums.append(c["name"])
        elif t == "date" or "timestamp" in t or "date" in t:
            dates.append(c["name"])
        elif t == "string" and 2 <= c.get("unique", 0) <= 50:
            cats.append(c["name"])
    return {"numeric": nums, "date": dates, "categorical": cats}


# ─── onboard ───────────────────────────────────────────────────────────────

def cmd_onboard(args: argparse.Namespace) -> int:
    """Single-shot: project + dataset + profile + seed questions, all in JSON."""
    # Lazy import — avoid circular and keep dataset.py free of any pull from here.
    import shutil
    from analyze import derive_insights  # noqa: E402

    src = Path(args.path).expanduser()
    if not src.exists():
        print(f"ERROR: file not found: {src}", file=sys.stderr)
        return 1

    # Project: get-or-create.
    proj = ws.get_project(args.slug)
    if proj is None:
        proj = ws.create_project(args.name or src.stem, description=args.description or "")
        slug = proj["slug"]
    else:
        slug = proj["slug"]
    dirs = ws.ensure_project_dirs(slug)

    is_excel = src.suffix.lower() in (".xlsx", ".xlsm", ".xls")
    raw_id = ws.new_id("raw_")
    raw_copy = dirs["datasets_raw"] / f"{raw_id}{src.suffix}"
    shutil.copy(src, raw_copy)

    datasets: list[dict] = []
    sheets = duck.xlsx_list_sheets(src) if is_excel else [None]
    base_name = src.stem
    for sheet in sheets:
        dataset_id = ws.new_id("ds_")
        parquet_path = dirs["datasets"] / f"{dataset_id}.parquet"
        try:
            info = duck.ingest(src, parquet_path, sheet=sheet)
        except SystemExit as exc:
            datasets.append({"sheet": sheet, "error": str(exc)})
            continue
        profile = duck.profile_parquet(parquet_path)
        ds_name = f"{base_name} · {sheet}" if sheet else base_name
        table = ws.slugify(ds_name).replace("-", "_") or dataset_id
        meta = {
            "id": dataset_id, "project": slug, "name": ds_name,
            "source_filename": src.name, "raw_path": str(raw_copy),
            "parquet": str(parquet_path), "sheet": sheet, "table": table,
            "rows": info["rows"], "columns": profile["columns"],
            "ingested_at": ws.now(), "tags": [],
        }
        ws.save_dataset(slug, meta)
        try:
            duck.register_parquet_table(ws.warehouse_path(slug), table, parquet_path)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: warehouse register failed for {table}: {exc}", file=sys.stderr)

        # Seed questions + insights so the agent has something to react to.
        from brainstorm import _questions  # noqa: E402
        rows_preview = duck.execute_sql(f"SELECT * FROM ds LIMIT 50", {"ds": parquet_path})
        header = rows_preview["columns"]
        body = [[str(v) if v is not None else "" for v in r] for r in rows_preview["rows"]]
        try:
            insights = derive_insights(header, body, profile["columns"])
        except Exception:  # noqa: BLE001 — insights are best-effort
            insights = []
        datasets.append({
            "schema": _schema_brief(meta),
            "questions": _questions(profile["columns"]),
            "insights": insights[:8],
        })

    _emit({
        "project": {"slug": slug, "name": proj["name"], "created": proj.get("created_at")},
        "ingested": [d for d in datasets if "error" not in d],
        "errors": [d for d in datasets if "error" in d],
    })
    return 0


# ─── brief ─────────────────────────────────────────────────────────────────

def cmd_brief(args: argparse.Namespace) -> int:
    """Dense JSON dump: project + dataset schemas + recent artifacts.

    Designed to be paste-once context for the LLM at the start of a turn so it
    knows what's available without 5 list/schema round-trips.
    """
    proj = ws.require_project(args.slug)
    datasets = [_schema_brief(d) for d in ws.list_datasets(args.slug)]
    arts = ws.list_artifacts(args.slug)

    chat_id = _resolve_chat_id(args.chat_id)
    visible = []
    for a in arts:
        scope = a.get("scope") or "project"
        if scope == "chat" and chat_id and a.get("chat_id") != chat_id:
            continue
        visible.append({
            "id": a["id"], "title": a.get("title"),
            "question": a.get("question"), "rows": a.get("row_count"),
            "scope": scope, "created_at": a.get("created_at"),
        })
    visible.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    _emit({
        "project": {"slug": proj["slug"], "name": proj["name"]},
        "datasets": datasets,
        "artifacts": visible[: args.artifact_limit],
        "warehouse": str(ws.warehouse_path(args.slug)),
        "hint": "Query the warehouse by table name (see datasets[].table). "
                "Use `da scripts/sql.py run --slug ... --sql ...`. "
                "Save findings with `da scripts/sql.py save --scope chat`.",
    })
    return 0


# ─── scan ──────────────────────────────────────────────────────────────────

def cmd_scan(args: argparse.Namespace) -> int:
    """Auto-anomaly across every (date col × numeric col) pair of a dataset.

    No need for the LLM to pick columns — surface top findings ranked by
    magnitude across the cartesian product.
    """
    ws.require_project(args.slug)
    d = ws.get_dataset(args.slug, args.id) or next(
        (x for x in ws.list_datasets(args.slug) if x["id"].startswith(args.id)), None
    )
    if not d:
        print(f"ERROR: dataset not found: {args.id}", file=sys.stderr)
        return 1

    cls = _classify_columns(d["columns"])
    date_cols = cls["date"] or []
    num_cols = cls["numeric"] or []
    # If no explicit date column, fall back to row order — useful for sequential
    # data that wasn't typed as date (e.g. snapshot # or seq id).
    order_cols = date_cols or ["__rownum__"]

    parquet = str(Path(d["parquet"])).replace("'", "''")
    findings: list[dict] = []
    cap_per_pair = max(int(args.limit_per_pair), 1)
    w = max(int(args.window), 2)
    sw = max(int(args.step_window), 2)

    for order in order_cols:
        for v in num_cols:
            v_s = v.replace('"', '""')
            if order == "__rownum__":
                order_expr = "ROW_NUMBER() OVER ()"
                ts_expr = "ROW_NUMBER() OVER ()"
            else:
                o_s = order.replace('"', '""')
                order_expr = f'"{o_s}"'
                ts_expr = f'"{o_s}"'
            sql = f"""
            WITH src AS (
              SELECT {ts_expr} AS ts, CAST("{v_s}" AS DOUBLE) AS val
              FROM read_parquet('{parquet}')
              WHERE "{v_s}" IS NOT NULL
            ),
            ord AS (SELECT ts, val, ROW_NUMBER() OVER (ORDER BY {order_expr}) AS rn FROM src)
            SELECT ts, val,
              AVG(val)         OVER (ORDER BY rn ROWS BETWEEN {w} PRECEDING AND 1 PRECEDING) AS m_pre,
              STDDEV_SAMP(val) OVER (ORDER BY rn ROWS BETWEEN {w} PRECEDING AND 1 PRECEDING) AS s_pre,
              LAG(val, 1)      OVER (ORDER BY rn) AS prev_val,
              AVG(val)         OVER (ORDER BY rn ROWS BETWEEN {sw} PRECEDING AND 1 PRECEDING) AS m_b,
              STDDEV_SAMP(val) OVER (ORDER BY rn ROWS BETWEEN {sw} PRECEDING AND 1 PRECEDING) AS s_b,
              AVG(val)         OVER (ORDER BY rn ROWS BETWEEN CURRENT ROW AND {sw - 1} FOLLOWING) AS m_a,
              STDDEV_SAMP(val) OVER (ORDER BY rn ROWS BETWEEN CURRENT ROW AND {sw - 1} FOLLOWING) AS s_a
            FROM ord ORDER BY rn
            """
            try:
                result = duck.execute_sql(sql, {})
            except Exception as exc:  # noqa: BLE001
                findings.append({"order_col": order, "value_col": v, "error": str(exc)})
                continue

            pair_finds: list[dict] = []
            for row in result["rows"]:
                ts, val, m_pre, s_pre, prev_val, m_b, s_b, m_a, s_a = row
                try:
                    vv = float(val)
                except (TypeError, ValueError):
                    continue
                if m_pre is not None and s_pre and s_pre > 0:
                    z = (vv - m_pre) / s_pre
                    if abs(z) >= args.z:
                        pair_finds.append({
                            "kind": "outlier", "order_col": order, "value_col": v,
                            "ts": str(ts), "value": vv, "magnitude": round(abs(z), 3),
                        })
                if prev_val is not None:
                    try:
                        pv = float(prev_val)
                        if pv != 0:
                            r = (vv - pv) / abs(pv)
                            if abs(r) >= args.ratio:
                                pair_finds.append({
                                    "kind": "spike", "order_col": order, "value_col": v,
                                    "ts": str(ts), "value": vv,
                                    "magnitude": round(abs(r), 3),
                                })
                    except (TypeError, ValueError):
                        pass
                if m_b is not None and m_a is not None:
                    pooled = ((s_b or 0.0) ** 2 + (s_a or 0.0) ** 2) ** 0.5
                    if pooled > 0:
                        step = (m_a - m_b) / pooled
                        if abs(step) >= args.step_z:
                            pair_finds.append({
                                "kind": "step", "order_col": order, "value_col": v,
                                "ts": str(ts), "magnitude": round(abs(step), 3),
                                "mean_before": round(m_b, 4), "mean_after": round(m_a, 4),
                            })
            pair_finds.sort(key=lambda x: x.get("magnitude", 0), reverse=True)
            findings.extend(pair_finds[:cap_per_pair])

    findings.sort(key=lambda x: x.get("magnitude", 0), reverse=True)
    _emit({
        "dataset_id": d["id"], "scanned_pairs": len(num_cols) * len(order_cols),
        "params": {"window": w, "z": args.z, "ratio": args.ratio,
                   "step_window": sw, "step_z": args.step_z},
        "finding_count": len(findings),
        "findings": findings[: args.limit],
    })
    return 0


# ─── recall ────────────────────────────────────────────────────────────────

def cmd_recall(args: argparse.Namespace) -> int:
    """Try to answer the question from prior artifacts before any new SQL.

    Returns:
      * confident hit  → cached answer (top artifact metadata) + 'use_cache=true'
      * weak hit       → list of candidates so LLM can decide
      * no hit         → empty matches; LLM should plan SQL afresh
    """
    ws.require_project(args.slug)
    arts = ws.list_artifacts(args.slug)
    chat_id = _resolve_chat_id(args.chat_id)
    # Same visibility rule as `artifact list --scope project` (default).
    visible = []
    for a in arts:
        scope = a.get("scope") or "project"
        if scope == "project":
            visible.append(a)
        elif scope == "chat" and chat_id and a.get("chat_id") == chat_id:
            visible.append(a)

    hits = retrieve(args.question, visible, top_k=args.top_k)
    matches = [{
        "score": round(s, 3),
        "id": a["id"], "title": a.get("title"),
        "question": a.get("question"),
        "rows": a.get("row_count"), "columns": a.get("columns"),
        "sql": a.get("sql"),
    } for a, s in hits]

    confident = bool(matches) and matches[0]["score"] >= args.confidence
    _emit({
        "use_cache": confident,
        "top_score": matches[0]["score"] if matches else 0,
        "matches": matches,
    })
    return 0


# ─── next ──────────────────────────────────────────────────────────────────

def cmd_next(args: argparse.Namespace) -> int:
    """Suggest 3-5 next analysis moves grounded in current project state.

    Reads schemas + existing artifacts, surfaces gaps (untouched datasets,
    columns with no chart yet, time series with no anomaly scan), and returns
    concrete commands the agent can execute.
    """
    ws.require_project(args.slug)
    datasets = ws.list_datasets(args.slug)
    arts = ws.list_artifacts(args.slug)
    examined = {a.get("title", "").lower() for a in arts}
    examined |= {(a.get("question") or "").lower() for a in arts}

    moves: list[dict] = []
    for d in datasets:
        cls = _classify_columns(d["columns"])
        ds_label = d["name"]
        # Untouched dataset → suggest a brief.
        any_arts = any(d["id"] in (a.get("source_datasets") or []) for a in arts)
        if not any_arts:
            moves.append({
                "intent": "explore",
                "reason": f"No artifacts yet reference {ds_label} ({d['rows']} rows).",
                "command": f"da scripts/sql.py run --slug {args.slug} "
                           f"--sql 'SELECT COUNT(*), COUNT(DISTINCT *) FROM \"{d.get('table') or d['id']}\"'",
            })
        # Time series → anomaly scan.
        if cls["date"] and cls["numeric"]:
            moves.append({
                "intent": "anomaly_scan",
                "reason": f"{ds_label} has date×numeric columns ({cls['date'][0]} × {cls['numeric'][0]}…).",
                "command": f"da scripts/agent.py scan --slug {args.slug} --id {d['id']}",
            })
        # Categorical × numeric → groupby chart candidate.
        if cls["categorical"] and cls["numeric"]:
            c, n = cls["categorical"][0], cls["numeric"][0]
            if f"{n} by {c}".lower() not in examined:
                moves.append({
                    "intent": "groupby",
                    "reason": f"{n} likely varies by {c} — segment to see who drives totals.",
                    "command": (
                        f"da scripts/sql.py save --slug {args.slug} "
                        f"--title '{n} by {c}' --question 'How does {n} split by {c}?' "
                        f"--sql 'SELECT \"{c}\", SUM(\"{n}\") AS total "
                        f"FROM \"{d.get('table') or d['id']}\" GROUP BY 1 ORDER BY 2 DESC'"
                    ),
                })

    _emit({"suggestions": moves[: args.limit]})
    return 0


# ─── analyze-loop: pin / pins / unpin / report ─────────────────────────────
#
# Workflow this surfaces:
#   1. agent builds a chart (viz_agent generate --save)  →  chart_id
#   2. agent writes an analysis paragraph for the user
#   3. agent calls `pin --chart-id X --note "..."`
#   4. loop steps 1-3
#   5. agent calls `report` → PDF with embedded chart tiles + the notes
#
# Storage is one append-only JSONL under <project>/pins.jsonl. No new schema —
# pins reference existing chart records by id so a single source of truth.

def _pins_file(slug: str) -> Path:
    return ws.project_root(slug) / "pins.jsonl"


def _read_pins(slug: str) -> list[dict]:
    p = _pins_file(slug)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _write_pins(slug: str, pins: list[dict]) -> None:
    p = _pins_file(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in pins) + "\n", encoding="utf-8")


def cmd_pin(args: argparse.Namespace) -> int:
    """Pin a chart (with an analysis note) for inclusion in the next report."""
    ws.require_project(args.slug)
    chart = ws.get_chart(args.slug, args.chart_id) or next(
        (c for c in ws.list_charts(args.slug) if c["id"].startswith(args.chart_id)),
        None,
    )
    if not chart:
        print(f"ERROR: chart not found: {args.chart_id}", file=sys.stderr)
        return 1

    pins = _read_pins(args.slug)
    record = {
        "id": ws.new_id("pin_"),
        "chart_id": chart["id"],
        "title": args.title or chart.get("title") or "(untitled)",
        "note": args.note or "",
        "chat_id": _resolve_chat_id(args.chat_id),
        "created_at": ws.now(),
        "order": len(pins),
    }
    pins.append(record)
    _write_pins(args.slug, pins)
    _emit({"pinned": record, "total_pins": len(pins)})
    return 0


def cmd_pins(args: argparse.Namespace) -> int:
    pins = _read_pins(args.slug)
    chat_id = _resolve_chat_id(args.chat_id)
    if args.scope == "chat":
        pins = [p for p in pins if chat_id and p.get("chat_id") == chat_id]
    _emit({
        "count": len(pins),
        "pins": [{
            "id": p["id"], "chart_id": p["chart_id"],
            "title": p.get("title"), "note": (p.get("note") or "")[:140],
            "order": p.get("order"), "created_at": p.get("created_at"),
        } for p in pins],
    })
    return 0


def cmd_unpin(args: argparse.Namespace) -> int:
    pins = _read_pins(args.slug)
    before = len(pins)
    pins = [p for p in pins if not (p["id"] == args.id or p["chart_id"] == args.id or p["id"].startswith(args.id))]
    # Renormalise order.
    for i, p in enumerate(pins):
        p["order"] = i
    _write_pins(args.slug, pins)
    _emit({"removed": before - len(pins), "remaining": len(pins)})
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Compile pinned charts + notes → PDF with embedded chart tiles.

    The agent decides WHEN to call this (when it judges the analysis is
    'enough'). No threshold or auto-trigger here — that's the LLM's call.
    """
    # Late import: report.py pulls heavyweight html/PDF dependencies.
    from report import _render_html, _html_to_pdf
    import tempfile

    proj = ws.require_project(args.slug)
    pins = _read_pins(args.slug)
    if args.scope == "chat":
        cid = _resolve_chat_id(args.chat_id)
        pins = [p for p in pins if cid and p.get("chat_id") == cid]
    if not pins:
        print("ERROR: no pins to report — pin at least one chart first", file=sys.stderr)
        return 1
    pins.sort(key=lambda p: p.get("order", 0))

    # Build markdown: title block → each pin as section with embedded chart.
    lines: list[str] = []
    lines.append(f"# {args.title or proj['name']}")
    if args.subtitle:
        lines.append(f"> {args.subtitle}")
    lines.append("")
    if args.intro:
        lines.append(args.intro)
        lines.append("")
    for i, p in enumerate(pins, 1):
        lines.append(f"## {i}. {p.get('title') or 'Finding'}")
        lines.append("")
        lines.append(f"![[{p['chart_id']}]]")
        lines.append("")
        if p.get("note"):
            lines.append(p["note"].strip())
            lines.append("")
    if args.outro:
        lines.append("---")
        lines.append("")
        lines.append(args.outro)

    md_text = "\n".join(lines)
    out_pdf = Path(args.out).expanduser()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)

    if args.md_out:
        Path(args.md_out).expanduser().write_text(md_text, encoding="utf-8")

    html_doc = _render_html(
        md_text,
        title=args.title or proj["name"],
        slug=args.slug,
        cover=not args.no_cover,
        subtitle=args.subtitle or "",
        author=args.author or "",
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html_doc)
        tmp_path = Path(tmp.name)
    try:
        _html_to_pdf(tmp_path, out_pdf)
    finally:
        tmp_path.unlink(missing_ok=True)

    size_kb = out_pdf.stat().st_size / 1024
    _emit({
        "pdf": str(out_pdf),
        "size_kb": round(size_kb, 1),
        "pins_used": len(pins),
        "title": args.title or proj["name"],
    })
    return 0


# ─── CLI wiring ────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Agentic surface for data_analysis.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_on = sub.add_parser("onboard", help="create project + ingest + profile + seed brief")
    p_on.add_argument("--slug", required=True, help="project slug (created if missing)")
    p_on.add_argument("--path", required=True)
    p_on.add_argument("--name", help="display name for project (only used when creating)")
    p_on.add_argument("--description", help="optional project description")
    p_on.set_defaults(fn=cmd_onboard)

    p_br = sub.add_parser("brief", help="dense JSON dump of project context")
    p_br.add_argument("--slug", required=True)
    p_br.add_argument("--artifact-limit", dest="artifact_limit", type=int, default=10)
    p_br.add_argument("--chat-id", dest="chat_id")
    p_br.set_defaults(fn=cmd_brief)

    p_sc = sub.add_parser("scan", help="auto-anomaly scan across all date×numeric pairs")
    p_sc.add_argument("--slug", required=True)
    p_sc.add_argument("--id", required=True, help="dataset id or id prefix")
    p_sc.add_argument("--window", type=int, default=20)
    p_sc.add_argument("--z", type=float, default=3.0)
    p_sc.add_argument("--ratio", type=float, default=0.5)
    p_sc.add_argument("--step-window", dest="step_window", type=int, default=10)
    p_sc.add_argument("--step-z", dest="step_z", type=float, default=3.0)
    p_sc.add_argument("--limit", type=int, default=50)
    p_sc.add_argument("--limit-per-pair", dest="limit_per_pair", type=int, default=5)
    p_sc.set_defaults(fn=cmd_scan)

    p_rc = sub.add_parser("recall", help="answer-from-memory for a question")
    p_rc.add_argument("--slug", required=True)
    p_rc.add_argument("--question", required=True)
    p_rc.add_argument("--top-k", type=int, default=5)
    p_rc.add_argument("--confidence", type=float, default=0.45,
                      help="min score to flag use_cache=true (default 0.45)")
    p_rc.add_argument("--chat-id", dest="chat_id")
    p_rc.set_defaults(fn=cmd_recall)

    p_nx = sub.add_parser("next", help="suggest 3-5 concrete next analysis moves")
    p_nx.add_argument("--slug", required=True)
    p_nx.add_argument("--limit", type=int, default=5)
    p_nx.set_defaults(fn=cmd_next)

    # ── Analyse-loop primitives ────────────────────────────────────────────
    p_pn = sub.add_parser("pin", help="pin a chart + analysis note for the next report")
    p_pn.add_argument("--slug", required=True)
    p_pn.add_argument("--chart-id", dest="chart_id", required=True, help="chart id or prefix")
    p_pn.add_argument("--note", required=True, help="narrative paragraph to show under the chart")
    p_pn.add_argument("--title", help="override chart title in the report")
    p_pn.add_argument("--chat-id", dest="chat_id")
    p_pn.set_defaults(fn=cmd_pin)

    p_ps = sub.add_parser("pins", help="list pinned charts for the in-progress report")
    p_ps.add_argument("--slug", required=True)
    p_ps.add_argument("--scope", choices=("all", "chat"), default="all")
    p_ps.add_argument("--chat-id", dest="chat_id")
    p_ps.set_defaults(fn=cmd_pins)

    p_up = sub.add_parser("unpin", help="remove a pin by id (or chart id) prefix")
    p_up.add_argument("--slug", required=True)
    p_up.add_argument("--id", required=True)
    p_up.set_defaults(fn=cmd_unpin)

    p_rp = sub.add_parser("report", help="compile pinned charts + notes into a PDF")
    p_rp.add_argument("--slug", required=True)
    p_rp.add_argument("--out", required=True, help="output PDF path")
    p_rp.add_argument("--title")
    p_rp.add_argument("--subtitle")
    p_rp.add_argument("--author")
    p_rp.add_argument("--intro", help="paragraph shown before the findings")
    p_rp.add_argument("--outro", help="paragraph shown after the findings")
    p_rp.add_argument("--no-cover", dest="no_cover", action="store_true")
    p_rp.add_argument("--scope", choices=("all", "chat"), default="all",
                      help="'chat' = only pins from this chat; 'all' = every pin in the project")
    p_rp.add_argument("--chat-id", dest="chat_id")
    p_rp.add_argument("--md-out", dest="md_out", help="optional: also save the generated markdown")
    p_rp.set_defaults(fn=cmd_report)

    args = p.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
