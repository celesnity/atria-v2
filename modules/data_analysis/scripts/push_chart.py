#!/usr/bin/env python
"""Push a chart preview block into the active chat session.

Two modes:
  --spec <file>   : push a pre-built spec saved by chart.py spec --save
  --kind <kind>   : build a spec on the fly from --path and column args,
                    then push it.

The block renders Vega-Lite. Save and Pin buttons inside the block emit
plain-text chat messages that name the exact CLI commands the agent
should run (same convention as warehouse/item_form).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _push(session_id: str, api_base: str, block: str, props: dict, title: str) -> int:
    body = json.dumps({
        "session_id": session_id,
        "module": "data_analysis",
        "block": block,
        "props": props,
        "title": title,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/blocks/push",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: push failed ({exc.code}): {detail}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"ERROR: cannot reach {api_base}: {exc.reason}", file=sys.stderr)
        return 1
    print(f"pushed {block} block: id={payload.get('block_id')}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Push chart block to chat.")
    parser.add_argument("--spec", help="path to chart spec JSON file (saved by chart.py spec --save)")
    parser.add_argument("--path", help="data file (CSV/Excel) — required with --kind")
    parser.add_argument("--sheet")
    parser.add_argument("--kind", choices=["bar", "line", "area", "scatter", "hist", "pie", "heatmap"])
    parser.add_argument("--x")
    parser.add_argument("--y")
    parser.add_argument("--color")
    parser.add_argument("--bins", type=int, default=20)
    parser.add_argument("--title", help="block title")
    args = parser.parse_args(argv[1:])

    session_id = os.environ.get("ATRIA_SESSION_ID")
    api_base = os.environ.get("ATRIA_API_BASE")
    if not session_id or not api_base:
        print("ERROR: ATRIA_SESSION_ID / ATRIA_API_BASE not set.", file=sys.stderr)
        return 2

    if args.spec:
        spec_doc = json.loads(Path(args.spec).expanduser().read_text(encoding="utf-8"))
    elif args.kind and args.path:
        from chart import KINDS, _rows_to_records  # type: ignore
        from analyze import load, _to_num  # type: ignore  # noqa: F401
        header, rows, path = load(args.path, sheet=int(args.sheet) if args.sheet and args.sheet.isdigit() else args.sheet)
        records = _rows_to_records(header, rows)
        builder = KINDS[args.kind]
        kwargs = {}
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
        spec_doc = {
            "path": str(path),
            "kind": args.kind,
            "title": args.title or spec.get("title"),
            "spec": spec,
            "vega_lib": "https://cdn.jsdelivr.net/npm/vega-lite@5",
        }
    else:
        print("ERROR: pass --spec FILE or --kind+--path+columns.", file=sys.stderr)
        return 2

    title = args.title or spec_doc.get("title") or "Chart preview"
    props = {"chart": spec_doc}
    return _push(session_id, api_base, "chart_preview", props, title)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
