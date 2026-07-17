"""Starter/scaffolding templates for module creation.

Pure string builders for the ``blank``/``skill``/``data`` module templates,
split out of ``store.py`` so the store CRUD logic reads without wading through
large embedded HTML/markdown/script blobs. No store logic lives here.
"""

from __future__ import annotations

import json
from typing import List, Optional

def _starter_skill_md(name: str, summary: str = "") -> str:
    body = summary or "Describe what this module does and when to use it."
    return (
        f"# {name}\n\n"
        f"{body}\n\n"
        "## When to use\n- describe trigger conditions\n\n"
        "## How to use\n"
        f"Run scripts via the bash tool: `python <modules>/{name}/scripts/<name>.py`\n"
        "(``<modules>`` resolves to the active modules directory — see the SKILL block "
        "header in the system prompt.)\n"
    )

def _starter_main_script() -> str:
    return (
        "#!/usr/bin/env python\n"
        '"""Entry point for this module."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def main() -> None:\n"
        '    print("hello from module")\n\n\n'
        'if __name__ == "__main__":\n'
        "    main()\n"
    )

def _starter_manifest_json(name: str, has_dashboard: bool) -> str:
    """Scaffolded manifest.json — covers the v1 sidebar + dashboard fields."""
    payload: dict = {
        "display_name": name.replace("_", " ").replace("-", " ").title(),
        "tooltip": f"Open the {name} module",
        "icon": "icon.svg",
    }
    if has_dashboard:
        payload["dashboard"] = {
            "title": f"{name.replace('_', ' ').replace('-', ' ').title()} · dashboard",
            "default_height": 720,
            "badge_color": "warning",
        }
    return json.dumps(payload, indent=2) + "\n"

def _starter_dashboard_html(name: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        f"  <title>{name} dashboard</title>\n"
        "  <style>body{font-family:system-ui;padding:2rem;color:#222}</style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{name}</h1>\n"
        "  <p>Edit this template to build your module's dashboard.</p>\n"
        "</body>\n"
        "</html>\n"
    )

_GENERIC_DATA_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
    '<ellipse cx="12" cy="5" rx="8" ry="3"/>'
    '<path d="M4 5v6c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/>'
    '<path d="M4 11v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/></svg>\n'
)

_GENERIC_DATA_SCRIPT = '''#!/usr/bin/env python
"""Generic CSV explorer for a data module (auto-generated).

All subcommands print JSON to stdout:
  list                                          -> {"datasets":[{name,rows,columns,size}]}
  preview --file F [--limit N]                  -> {"file","columns","rows":[[...]]}
  query --file F [--filter S] [--column C] [--limit N]

CSV datasets live in ../data/ next to this script.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _csv_files():
    if not DATA_DIR.is_dir():
        return []
    return sorted(p for p in DATA_DIR.rglob("*.csv") if p.is_file())


def _rel(p: Path) -> str:
    return p.relative_to(DATA_DIR).as_posix()


def _resolve(file: str) -> Path:
    p = (DATA_DIR / file).resolve()
    try:
        p.relative_to(DATA_DIR.resolve())
    except ValueError:
        raise SystemExit(f"path outside data dir: {file}")
    if not p.is_file():
        raise SystemExit(f"file not found: {file}")
    return p


def _header_and_count(path: Path):
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        count = sum(1 for _ in reader)
    return header, count


def cmd_list() -> dict:
    out = []
    for p in _csv_files():
        try:
            header, count = _header_and_count(p)
            size = p.stat().st_size
        except OSError:
            continue
        out.append({"name": _rel(p), "rows": count, "columns": header, "size": size})
    return {"datasets": out}


def cmd_preview(file: str, limit: int) -> dict:
    p = _resolve(file)
    with p.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        rows = []
        for row in reader:
            if len(rows) >= limit:
                break
            rows.append(row)
    return {"file": file, "columns": header, "rows": rows}


def cmd_query(file: str, filter_s: str, column: str, limit: int) -> dict:
    p = _resolve(file)
    with p.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        col_idx = header.index(column) if column and column in header else None
        needle = (filter_s or "").lower()
        rows = []
        for row in reader:
            if needle:
                if col_idx is not None:
                    hay = row[col_idx] if col_idx < len(row) else ""
                else:
                    hay = " ".join(row)
                if needle not in hay.lower():
                    continue
            rows.append(row)
            if len(rows) >= limit:
                break
    return {"file": file, "columns": header, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description="Generic CSV explorer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_prev = sub.add_parser("preview")
    p_prev.add_argument("--file", required=True)
    p_prev.add_argument("--limit", type=int, default=100)
    p_q = sub.add_parser("query")
    p_q.add_argument("--file", required=True)
    p_q.add_argument("--filter", default="")
    p_q.add_argument("--column", default="")
    p_q.add_argument("--limit", type=int, default=100)
    # Tolerate a stray --json flag from dashboard callers.
    for sp in (sub.choices["list"], p_prev, p_q):
        sp.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.cmd == "list":
        result = cmd_list()
    elif args.cmd == "preview":
        result = cmd_preview(args.file, args.limit)
    else:
        result = cmd_query(args.file, args.filter, args.column, args.limit)
    json.dump(result, sys.stdout, default=str)
    sys.stdout.write("\\n")


if __name__ == "__main__":
    main()
'''

def _data_manifest_json(name: str) -> str:
    title = name.replace("_", " ").replace("-", " ").title()
    payload = {
        "display_name": title,
        "tooltip": f"Explore the {title} datasets",
        "icon": "icon.svg",
        "dashboard": {
            "title": f"{title} · data",
            "default_height": 720,
            "badge_color": "info",
        },
    }
    return json.dumps(payload, indent=2) + "\n"

def _data_skill_md(name: str, summary: str, datasets: Optional[List[dict]]) -> str:
    lines = [
        f"# {name}",
        "",
        summary or "Data module created from uploaded files.",
        "",
        "## When to use",
        f"- When the user asks about the datasets bundled in the {name} module.",
        "",
        "## Data",
        f"CSV datasets live in `<modules>/{name}/data/` (original uploads such as "
        ".xlsx are kept alongside their converted .csv).",
        "",
    ]
    if datasets:
        lines.append("### Datasets")
        for ds in datasets:
            cols = ", ".join(ds.get("columns", [])[:20]) or "(no header)"
            lines.append(f"- `{ds['name']}` - {ds.get('rows', 0)} rows. Columns: {cols}")
        lines.append("")
    lines += [
        "## How to use",
        "Run the data explorer via the bash tool (`<modules>` resolves to the active "
        "modules directory - see the SKILL block header in the system prompt):",
        f"- `python <modules>/{name}/scripts/data.py list` - datasets, row counts, columns",
        f"- `python <modules>/{name}/scripts/data.py preview --file <file.csv> --limit 20`",
        f"- `python <modules>/{name}/scripts/data.py query --file <file.csv> --filter <text> "
        "[--column <col>]`",
        "",
        "The dashboard (`dashboard.html`) lists the datasets and renders any CSV as a "
        "sortable, filterable table. Hand-tailor it (domain KPIs, charts) by editing "
        "`dashboard.html`.",
        "",
    ]
    return "\n".join(lines)
