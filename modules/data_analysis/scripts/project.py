#!/usr/bin/env python
"""Project workspace CLI (FR-PROJ-*).

Subcommands: list, create, show.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import workspace as ws  # noqa: E402


def cmd_list(args: argparse.Namespace) -> int:
    projects = ws.list_projects()
    if args.json:
        print(json.dumps(projects, ensure_ascii=False))
        return 0
    if not projects:
        print("(no projects)")
        return 0
    for p in projects:
        print(f"  [{p['slug']:<24}] {p['name']}  ·  updated {p['updated_at']}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    meta = ws.create_project(args.name, description=args.description or "")
    print(f"created: {meta['slug']}  ({meta['id']})")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    meta = ws.require_project(args.slug)
    out = {
        "project": meta,
        "datasets": [{"id": d["id"], "name": d["name"], "rows": d.get("rows")} for d in ws.list_datasets(args.slug)],
        "artifacts": [{"id": a["id"], "title": a.get("title")} for a in ws.list_artifacts(args.slug)],
        "charts": [{"id": c["id"], "title": c.get("title")} for c in ws.list_charts(args.slug)],
        "traces": [{"id": t["id"], "query": t.get("query")} for t in ws.list_traces(args.slug)],
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
        return 0
    print(f"project:   {meta['name']}  ({meta['slug']})")
    print(f"created:   {meta['created_at']}    updated: {meta['updated_at']}")
    for section, items in (("datasets", out["datasets"]), ("artifacts", out["artifacts"]),
                           ("charts", out["charts"]), ("traces", out["traces"])):
        print(f"\n{section} ({len(items)}):")
        for it in items:
            label = it.get("title") or it.get("name") or it.get("query") or "(untitled)"
            print(f"  [{it['id'][:8]}] {label}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Data-analysis project workspace.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ls = sub.add_parser("list", help="list projects")
    p_ls.add_argument("--json", action="store_true")
    p_ls.set_defaults(fn=cmd_list)

    p_new = sub.add_parser("create", help="create a new project")
    p_new.add_argument("--name", required=True)
    p_new.add_argument("--description", default="")
    p_new.set_defaults(fn=cmd_create)

    p_sh = sub.add_parser("show", help="show a project summary")
    p_sh.add_argument("--slug", required=True)
    p_sh.add_argument("--json", action="store_true")
    p_sh.set_defaults(fn=cmd_show)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
