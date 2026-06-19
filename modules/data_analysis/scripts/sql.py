#!/usr/bin/env python
"""DuckDB SQL execution + artifact persistence.

This is the public surface for the Data Agent's `execute_sql` and
`save_artifact` tools (PRD §9). Generated SQL is always visible
(FR-SQL-01) and re-runnable (FR-SQL-02).

Subcommands:
  run    — execute a SQL string or @file; print rows as JSON
  save   — execute + persist the result as a Project Artifact
  trace  — record an execution trace tying query→plan→sql→artifact (FR-TRACE-*)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import duck, workspace as ws  # noqa: E402


def _resolve_sql(arg: str) -> str:
    if arg.startswith("@"):
        return Path(arg[1:]).expanduser().read_text(encoding="utf-8")
    return arg


def _views_for(slug: str, dataset_ids: list[str] | None) -> dict[str, Path]:
    """Map view-name → parquet path for each registered dataset.

    Prefers the explicit ``table`` field (a SQL-safe identifier set at ingest
    time — needed because per-sheet datasets have names like "Iris · Sheet1"
    that don't survive the safe-name strip in execute_sql).
    """
    datasets = ws.list_datasets(slug)
    if dataset_ids:
        prefixes = list(dataset_ids)
        datasets = [d for d in datasets if any(d["id"].startswith(p) for p in prefixes)]
    return {(d.get("table") or d["name"]): Path(d["parquet"]) for d in datasets}


def cmd_run(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    views = _views_for(args.slug, args.use)
    sql = _resolve_sql(args.sql)
    result = duck.execute_sql(sql, views)
    if args.text:
        cols = result["columns"]
        widths = [max(len(c), 6) for c in cols]
        preview = result["rows"][: args.limit]
        for r in preview:
            for i, v in enumerate(r):
                widths[i] = max(widths[i], len(str(v)))
        print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cols)))
        print("  ".join("-" * w for w in widths))
        for r in preview:
            print("  ".join(str(v).ljust(widths[i]) for i, v in enumerate(r)))
        more = result["row_count"] - len(preview)
        suffix = f" (+{more} more — use save to materialise)" if more > 0 else ""
        print(f"\n{result['row_count']} rows{suffix}")
        return 0

    # JSON mode — cap rows to keep stdout small. Use --full to disable.
    rows = result["rows"] if args.full else result["rows"][: args.limit]
    out = {
        "sql": sql,
        "columns": result["columns"],
        "row_count": result["row_count"],
        "rows": rows,
        "truncated": (not args.full) and result["row_count"] > len(rows),
    }
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    proj = ws.require_project(args.slug)
    views = _views_for(args.slug, args.use)
    sql = _resolve_sql(args.sql)
    result = duck.execute_sql(sql, views)

    # Resolve scope. "chat" requires a chat id — fall back to project if the
    # host didn't expose ATRIA_SESSION_ID / didn't pass --chat-id explicitly,
    # so the call doesn't silently lose data.
    scope = (args.scope or "project").lower()
    chat_id = args.chat_id or os.environ.get("ATRIA_SESSION_ID") or os.environ.get("ATRIA_CONVERSATION_ID")
    if scope == "chat" and not chat_id:
        print("WARN: --scope chat requested but no chat id available — falling back to project", file=sys.stderr)
        scope = "project"

    art_id = ws.new_id("art_")
    dirs = ws.ensure_project_dirs(args.slug)
    parquet_path = dirs["artifacts"] / f"{art_id}.parquet"

    # Persist the result table as Parquet via DuckDB.
    con = duck.connect()
    try:
        for name, path in views.items():
            safe = "".join(ch for ch in name if ch.isalnum() or ch == "_")
            p = str(path).replace("'", "''")
            con.execute(f"CREATE VIEW {safe} AS SELECT * FROM read_parquet('{p}')")
        out_p = str(parquet_path).replace("'", "''")
        con.execute(f"COPY ({sql}) TO '{out_p}' (FORMAT PARQUET)")
    finally:
        con.close()

    meta = {
        "id": art_id,
        "project": proj["slug"],
        "scope": scope,
        "chat_id": chat_id if scope == "chat" else None,
        "title": args.title or "(untitled artifact)",
        "question": args.question or "",
        "sql": sql,
        "columns": result["columns"],
        "dtypes": result["dtypes"],
        "row_count": result["row_count"],
        "parquet": str(parquet_path),
        "tags": args.tag or [],
        "created_at": ws.now(),
        "source_datasets": [k for k in views.keys()],
    }
    ws.save_artifact(args.slug, meta)
    scope_note = f" [scope={scope}{':'+chat_id if scope == 'chat' else ''}]"
    print(f"saved artifact: {art_id}{scope_note}  ({result['row_count']} rows)")
    if args.json:
        print(json.dumps(meta, ensure_ascii=False))
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    """Record an Execution Trace (FR-TRACE-*) — user-visible, no chain-of-thought."""
    proj = ws.require_project(args.slug)
    trace = {
        "id": ws.new_id("tr_"),
        "project": proj["slug"],
        "query": args.query,
        "plan": json.loads(args.plan) if args.plan else [],
        "actions": json.loads(args.actions) if args.actions else [],
        "sql": args.sql or "",
        "tools_used": (args.tools or "").split(",") if args.tools else [],
        "artifacts_created": (args.artifacts or "").split(",") if args.artifacts else [],
        "result_summary": args.summary or "",
        "created_at": ws.now(),
    }
    p = ws.save_trace(args.slug, trace)
    print(f"trace: {trace['id']}  → {p}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="DuckDB SQL + artifact tools.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="execute SQL against the project's datasets")
    p_run.add_argument("--slug", required=True)
    p_run.add_argument("--sql", required=True, help="SQL string, or @path/to/query.sql")
    p_run.add_argument("--use", action="append", help="restrict to dataset id prefix (repeatable)")
    p_run.add_argument("--text", action="store_true", help="human-readable table output")
    p_run.add_argument("--limit", type=int, default=20, help="max rows in stdout (default 20)")
    p_run.add_argument("--full", action="store_true", help="emit all rows (off by default to protect context)")
    p_run.set_defaults(fn=cmd_run)

    p_save = sub.add_parser("save", help="execute SQL + save result as a project artifact")
    p_save.add_argument("--slug", required=True)
    p_save.add_argument("--sql", required=True)
    p_save.add_argument("--use", action="append")
    p_save.add_argument("--title", required=True)
    p_save.add_argument("--question", help="natural-language question that produced this artifact")
    p_save.add_argument("--tag", action="append")
    p_save.add_argument("--scope", choices=("chat", "project"), default="project",
                        help="visibility: 'chat' = only this conversation, 'project' = all chats in the project")
    p_save.add_argument("--chat-id", dest="chat_id",
                        help="explicit chat/session id (defaults to $ATRIA_SESSION_ID)")
    p_save.add_argument("--json", action="store_true")
    p_save.set_defaults(fn=cmd_save)

    p_tr = sub.add_parser("trace", help="record an execution trace for a query turn")
    p_tr.add_argument("--slug", required=True)
    p_tr.add_argument("--query", required=True, help="user's natural-language question")
    p_tr.add_argument("--plan", help="JSON-encoded plan steps list")
    p_tr.add_argument("--actions", help="JSON-encoded list of agent actions")
    p_tr.add_argument("--sql", help="generated SQL")
    p_tr.add_argument("--tools", help="comma-separated tool names used")
    p_tr.add_argument("--artifacts", help="comma-separated artifact ids created")
    p_tr.add_argument("--summary", help="terse result summary (no chain-of-thought)")
    p_tr.set_defaults(fn=cmd_tr if False else cmd_trace)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
