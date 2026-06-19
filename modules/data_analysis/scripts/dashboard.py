#!/usr/bin/env python
"""Dashboard canvas CRUD.

The dashboard is a flat JSON file at data/dashboard.json holding a list of
pinned tiles. A tile is { id, title, kind, spec, layout: {x,y,w,h}, source }.
The dashboard.html viewer reads this file via the host server's static
mount (modules/<name>/data/...) and renders each tile with Vega-Lite.

Subcommands: list, pin, unpin, clear, move, rename, planning.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DASH_PATH = DATA_DIR / "dashboard.json"
PLAN_PATH = DATA_DIR / "planning.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> dict[str, Any]:
    if not DASH_PATH.exists():
        return {"tiles": [], "updated_at": _now()}
    try:
        return json.loads(DASH_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"tiles": [], "updated_at": _now()}


def _save(state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    DASH_PATH.parent.mkdir(parents=True, exist_ok=True)
    DASH_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_spec(spec_path: str) -> dict[str, Any]:
    p = Path(spec_path).expanduser()
    if not p.is_absolute():
        cand = DATA_DIR / "charts" / p
        if cand.exists():
            p = cand
    if not p.exists():
        raise SystemExit(f"ERROR: spec file not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _next_layout(tiles: list[dict[str, Any]], w: int, h: int) -> dict[str, int]:
    cols = 12
    if not tiles:
        return {"x": 0, "y": 0, "w": w, "h": h}
    rows = []
    for t in tiles:
        L = t.get("layout", {})
        rows.append((L.get("x", 0), L.get("y", 0), L.get("w", w), L.get("h", h)))
    y = max(y0 + h0 for _, y0, _, h0 in rows)
    return {"x": 0, "y": y, "w": w, "h": h}


def cmd_list(args: argparse.Namespace) -> int:
    state = _load()
    if args.json:
        print(json.dumps(state, ensure_ascii=False))
        return 0
    print(f"dashboard: {DASH_PATH}")
    print(f"updated:   {state.get('updated_at')}")
    print(f"tiles:     {len(state['tiles'])}")
    for t in state["tiles"]:
        L = t.get("layout", {})
        print(f"  [{t['id'][:6]}] {t.get('kind','?'):<8} {t.get('title','(untitled)')}  @({L.get('x',0)},{L.get('y',0)} {L.get('w',6)}×{L.get('h',4)})")
    return 0


def cmd_pin(args: argparse.Namespace) -> int:
    state = _load()
    spec_doc = _load_spec(args.spec)
    title = args.title or spec_doc.get("title") or spec_doc.get("kind", "chart")
    tile = {
        "id": str(uuid.uuid4()),
        "title": title,
        "kind": spec_doc.get("kind", "chart"),
        "source": spec_doc.get("path"),
        "spec": spec_doc.get("spec", spec_doc),
        "vega_lib": spec_doc.get("vega_lib"),
        "layout": _next_layout(state["tiles"], args.w, args.h),
        "created_at": _now(),
    }
    state["tiles"].append(tile)
    _save(state)
    print(f"pinned: {tile['id']}  '{title}'")
    return 0


def cmd_unpin(args: argparse.Namespace) -> int:
    state = _load()
    before = len(state["tiles"])
    state["tiles"] = [t for t in state["tiles"] if not t["id"].startswith(args.id)]
    if len(state["tiles"]) == before:
        print(f"ERROR: no tile matches id prefix '{args.id}'", file=sys.stderr)
        return 1
    _save(state)
    print(f"unpinned: {before - len(state['tiles'])} tile(s)")
    return 0


def cmd_clear(_args: argparse.Namespace) -> int:
    _save({"tiles": []})
    print(f"cleared: {DASH_PATH}")
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    state = _load()
    found = False
    for t in state["tiles"]:
        if t["id"].startswith(args.id):
            L = t.setdefault("layout", {})
            if args.x is not None: L["x"] = args.x
            if args.y is not None: L["y"] = args.y
            if args.w is not None: L["w"] = args.w
            if args.h is not None: L["h"] = args.h
            found = True
            break
    if not found:
        print(f"ERROR: no tile matches id prefix '{args.id}'", file=sys.stderr)
        return 1
    _save(state)
    print(f"moved: {args.id}")
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    state = _load()
    for t in state["tiles"]:
        if t["id"].startswith(args.id):
            t["title"] = args.title
            _save(state)
            print(f"renamed: {args.id} -> {args.title}")
            return 0
    print(f"ERROR: no tile matches id prefix '{args.id}'", file=sys.stderr)
    return 1


# ─── Planning (lightweight roadmap that survives across chats) ──────────

def _plan_load() -> dict[str, Any]:
    if not PLAN_PATH.exists():
        return {"goal": "", "steps": [], "updated_at": _now()}
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _plan_save(state: dict[str, Any]) -> None:
    state["updated_at"] = _now()
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_planning(args: argparse.Namespace) -> int:
    state = _plan_load()
    if args.action == "show":
        print(json.dumps(state, ensure_ascii=False) if args.json else
              _plan_render(state))
        return 0
    if args.action == "goal":
        state["goal"] = args.text or ""
        _plan_save(state)
        print(f"goal: {state['goal']}")
        return 0
    if args.action == "add":
        state["steps"].append({
            "id": str(uuid.uuid4())[:8],
            "text": args.text,
            "status": "todo",
        })
        _plan_save(state)
        print(f"added step: {args.text}")
        return 0
    if args.action == "done":
        for s in state["steps"]:
            if s["id"].startswith(args.id):
                s["status"] = "done"
                _plan_save(state)
                print(f"done: {s['text']}")
                return 0
        print(f"ERROR: no step id '{args.id}'", file=sys.stderr)
        return 1
    if args.action == "clear":
        _plan_save({"goal": "", "steps": []})
        print("planning cleared")
        return 0
    return 2


def _plan_render(state: dict[str, Any]) -> str:
    out = [f"goal:    {state.get('goal','(none)')}"]
    if not state.get("steps"):
        out.append("(no steps)")
    for s in state.get("steps", []):
        tick = "✓" if s["status"] == "done" else "·"
        out.append(f"  {tick} [{s['id']}] {s['text']}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Dashboard canvas + planning store.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ls = sub.add_parser("list", help="list pinned tiles")
    p_ls.add_argument("--json", action="store_true")
    p_ls.set_defaults(fn=cmd_list)

    p_pin = sub.add_parser("pin", help="pin a saved chart spec to the canvas")
    p_pin.add_argument("--spec", required=True, help="chart spec path (saved by chart.py spec --save)")
    p_pin.add_argument("--title")
    p_pin.add_argument("--w", type=int, default=6, help="tile width in 12-col grid (default 6)")
    p_pin.add_argument("--h", type=int, default=4, help="tile height in rows (default 4)")
    p_pin.set_defaults(fn=cmd_pin)

    p_un = sub.add_parser("unpin", help="remove a tile by id prefix")
    p_un.add_argument("--id", required=True)
    p_un.set_defaults(fn=cmd_unpin)

    p_clr = sub.add_parser("clear", help="remove all tiles")
    p_clr.set_defaults(fn=cmd_clear)

    p_mv = sub.add_parser("move", help="reposition / resize a tile")
    p_mv.add_argument("--id", required=True)
    p_mv.add_argument("--x", type=int)
    p_mv.add_argument("--y", type=int)
    p_mv.add_argument("--w", type=int)
    p_mv.add_argument("--h", type=int)
    p_mv.set_defaults(fn=cmd_move)

    p_rn = sub.add_parser("rename", help="rename a tile")
    p_rn.add_argument("--id", required=True)
    p_rn.add_argument("--title", required=True)
    p_rn.set_defaults(fn=cmd_rename)

    p_pl = sub.add_parser("planning", help="manage the analysis planning store")
    p_pl.add_argument("action", choices=["show", "goal", "add", "done", "clear"])
    p_pl.add_argument("--text", help="goal text or step text")
    p_pl.add_argument("--id", help="step id prefix (for 'done')")
    p_pl.add_argument("--json", action="store_true")
    p_pl.set_defaults(fn=cmd_planning)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
