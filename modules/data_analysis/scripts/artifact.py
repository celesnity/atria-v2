#!/usr/bin/env python
"""Artifact memory CLI (FR-ART-*).

Subcommands:
  list      — list artifacts in a project
  show      — print a single artifact's metadata + a head of its parquet
  search    — fuzzy semantic search over artifacts (FR-ART-03)
  retrieve  — Planner Agent tool: return top-k artifacts for a query as JSON
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import duck, workspace as ws  # noqa: E402
from core.retrieve import retrieve  # noqa: E402


def _filter_scope(arts: list[dict], scope: str | None, chat_id: str | None) -> list[dict]:
    """Filter artifacts by visibility scope.

    Legacy artifacts (no ``scope`` field) are treated as project-wide so older
    data stays visible. When ``scope='chat'``, only artifacts tagged with the
    same chat_id are returned; ``scope='all'`` (or None) returns everything.
    """
    if not scope or scope == "all":
        return arts
    out: list[dict] = []
    for a in arts:
        a_scope = a.get("scope") or "project"
        if scope == "project":
            # Project view: include project artifacts AND chat artifacts of THIS chat.
            if a_scope == "project":
                out.append(a)
            elif a_scope == "chat" and chat_id and a.get("chat_id") == chat_id:
                out.append(a)
        elif scope == "chat":
            if a_scope == "chat" and chat_id and a.get("chat_id") == chat_id:
                out.append(a)
    return out


def _resolve_chat_id(explicit: str | None) -> str | None:
    return explicit or os.environ.get("ATRIA_SESSION_ID") or os.environ.get("ATRIA_CONVERSATION_ID")


def cmd_list(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    arts = _filter_scope(ws.list_artifacts(args.slug), args.scope, _resolve_chat_id(args.chat_id))
    if args.json:
        print(json.dumps(arts, ensure_ascii=False))
        return 0
    if not arts:
        print("(no artifacts yet — created by Data Agent via sql.py save)")
        return 0
    for a in arts:
        tag = ""
        if a.get("scope") == "chat":
            tag = f" [chat:{(a.get('chat_id') or '')[:8]}]"
        print(f"  [{a['id'][:10]}] {a['title']:<40}  rows={a['row_count']:<5}  {a['created_at']}{tag}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    a = ws.get_artifact(args.slug, args.id) or next(
        (x for x in ws.list_artifacts(args.slug) if x["id"].startswith(args.id)), None
    )
    if not a:
        print(f"ERROR: artifact not found: {args.id}", file=sys.stderr)
        return 1
    print(f"artifact: {a['title']}  ({a['id']})")
    print(f"question: {a.get('question', '')}")
    print(f"created:  {a['created_at']}    rows={a['row_count']}")
    print(f"sources:  {', '.join(a.get('source_datasets', []))}")
    print(f"sql:\n{a['sql']}")
    head_n = min(int(args.head), 20)  # hard ceiling
    head = duck.execute_sql(f"SELECT * FROM art LIMIT {head_n}", {"art": Path(a["parquet"])})
    print(f"\nhead ({head_n} of {a['row_count']}):")
    for row in head["rows"]:
        print("  ", row)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    ws.require_project(args.slug)
    arts = _filter_scope(ws.list_artifacts(args.slug), args.scope, _resolve_chat_id(args.chat_id))
    hits = retrieve(args.query, arts, top_k=args.top_k)
    if args.json:
        print(json.dumps([{"score": s, "artifact": a} for a, s in hits], ensure_ascii=False))
        return 0
    if not hits:
        print("(no matches)")
        return 0
    for a, s in hits:
        print(f"  {s:.3f}  [{a['id'][:10]}] {a['title']}  — {a.get('question','')[:60]}")
    return 0


def cmd_retrieve(args: argparse.Namespace) -> int:
    """Tool surface for the Planner Agent (FR-PLAN-04)."""
    ws.require_project(args.slug)
    arts = _filter_scope(ws.list_artifacts(args.slug), args.scope, _resolve_chat_id(args.chat_id))
    hits = retrieve(args.query, arts, top_k=args.top_k)
    out = [{
        "score": round(s, 3),
        "id": a["id"],
        "title": a.get("title"),
        "question": a.get("question"),
        "columns": a.get("columns"),
        "row_count": a.get("row_count"),
        "sql": a.get("sql"),
    } for a, s in hits]
    print(json.dumps({"matches": out}, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Artifact memory store.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for cmd, fn, helptext in (
        ("list", cmd_list, "list project artifacts"),
        ("search", cmd_search, "lexical/semantic search across artifacts"),
        ("retrieve", cmd_retrieve, "tool: top-k artifacts for a query (JSON)"),
    ):
        p = sub.add_parser(cmd, help=helptext)
        p.add_argument("--slug", required=True)
        if cmd in ("search", "retrieve"):
            p.add_argument("--query", required=True)
            p.add_argument("--top-k", type=int, default=5)
        if cmd in ("list", "search"):
            p.add_argument("--json", action="store_true")
        # Scope filter — shared across list/search/retrieve.
        p.add_argument("--scope", choices=("chat", "project", "all"), default="project",
                       help="'project' (default) = project + this chat's items; 'chat' = only this chat; 'all' = ignore scope")
        p.add_argument("--chat-id", dest="chat_id",
                       help="explicit chat/session id (defaults to $ATRIA_SESSION_ID)")
        p.set_defaults(fn=fn)

    p_show = sub.add_parser("show", help="show artifact metadata + head")
    p_show.add_argument("--slug", required=True)
    p_show.add_argument("--id", required=True)
    p_show.add_argument("--head", type=int, default=5, help="preview row cap (hard ceiling 20)")
    p_show.set_defaults(fn=cmd_show)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
