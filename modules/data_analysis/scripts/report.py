#!/usr/bin/env python
"""Markdown → PDF report builder.

Two modes:

  render   — convert a hand-written .md file (with optional `![[chart_id]]`
             and `![[artifact_id]]` embeds) into a styled PDF.
  generate — auto-build a project digest (overview + datasets + artifacts +
             every pinned chart + execution-trace log) as Markdown, then
             render it to PDF.

Rendering uses headless Chrome (`--print-to-pdf`). Chrome binary
discovery order: $ATRIA_CHROME, then a list of common install paths.
Charts are inlined as Vega-Lite specs rendered by the host Chrome at
print time — no server-side image conversion needed.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import workspace as ws  # noqa: E402

try:
    import markdown as _md
except ImportError as exc:
    raise SystemExit("ERROR: `markdown` not installed. Run via the `da` launcher.") from exc


# ─── Chrome discovery ───────────────────────────────────────────────────

def _find_chrome() -> str:
    explicit = os.environ.get("ATRIA_CHROME")
    if explicit and Path(explicit).exists():
        return explicit
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chrome") or "",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise SystemExit(
        "ERROR: no Chrome / Chromium binary found. Install Chrome or set $ATRIA_CHROME."
    )


# ─── HTML template ──────────────────────────────────────────────────────

_PAGE_CSS = """
@page { size: A4; margin: 18mm 16mm 22mm 16mm; }
:root {
  --ink: #0a0a0a; --muted: #555; --hairline: #ddd; --soft: #f7f6f3;
  --accent: #F58A6B; --mint: #A7E3B8; --cream: #F5C26B;
}
html, body { background: #fff; color: var(--ink); }
body {
  font-family: 'Inter Variable', 'Inter', system-ui, -apple-system, sans-serif;
  font-size: 11.5pt; line-height: 1.55; margin: 0;
}
h1, h2, h3, h4 { font-weight: 600; letter-spacing: -0.01em; margin: 1.6em 0 .55em; }
h1 { font-size: 24pt; margin-top: 0; border-bottom: 2px solid var(--ink); padding-bottom: 8px; }
h2 { font-size: 16pt; border-bottom: 1px solid var(--hairline); padding-bottom: 4px; }
h3 { font-size: 13pt; color: #222; }
p, ul, ol { margin: .55em 0; }
ul, ol { padding-left: 1.4em; }
li { margin: .15em 0; }
code, pre {
  font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
  font-size: 9.5pt;
}
pre {
  background: var(--soft); border: 1px solid var(--hairline); border-radius: 6px;
  padding: 10px 12px; overflow-x: auto;
}
code { background: var(--soft); padding: 1px 5px; border-radius: 4px; }
pre code { background: transparent; padding: 0; }
blockquote {
  border-left: 3px solid var(--accent); margin: 1em 0;
  padding: .2em 0 .2em 12px; color: var(--muted);
}
table { border-collapse: collapse; width: 100%; margin: .8em 0; font-size: 10pt; }
th, td { border-bottom: 1px solid var(--hairline); padding: 6px 9px; text-align: left; }
th { background: var(--soft); font-weight: 600; }
hr { border: 0; border-top: 1px solid var(--hairline); margin: 1.6em 0; }
.cover {
  page-break-after: always;
  display: flex; flex-direction: column; justify-content: space-between;
  min-height: 235mm;
}
.cover .eyebrow {
  font-family: 'JetBrains Mono', SF Mono, Menlo, monospace;
  text-transform: uppercase; letter-spacing: 0.12em;
  font-size: 9.5pt; color: var(--muted);
}
.cover .title { font-size: 30pt; font-weight: 600; line-height: 1.15; }
.cover .meta {
  font-family: 'JetBrains Mono', SF Mono, Menlo, monospace;
  font-size: 10pt; color: var(--muted);
}
.cover .accent {
  width: 80px; height: 4px; background: var(--accent); margin: 14px 0 28px;
}

/* Chart tiles in the printed report */
.chart-tile {
  border: 1px solid var(--hairline); border-radius: 10px;
  margin: .8em 0; padding: 8px 12px 14px;
  page-break-inside: avoid;
}
.chart-tile header {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 6px;
}
.chart-tile header h4 { margin: 0; font-size: 11pt; }
.chart-tile header .kind {
  font-family: 'JetBrains Mono', SF Mono, Menlo, monospace;
  font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.06em;
  background: var(--mint); padding: 2px 7px; border-radius: 999px;
}
.chart-tile .vega { min-height: 240px; }

/* Compact trace + artifact tables */
.kvp { font-size: 10pt; color: var(--muted); margin: 4px 0; }
.kvp b { color: var(--ink); font-weight: 500; }
"""

_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<link rel="preconnect" href="https://rsms.me" crossorigin />
<link rel="stylesheet" href="https://rsms.me/inter/inter.css" />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" />
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<style>{css}</style>
</head>
<body>
{body}
<script>
  const specs = {specs_json};
  const promises = Object.entries(specs).map(([id, spec]) => {{
    const el = document.getElementById('vega-' + id);
    if (!el || !spec) return Promise.resolve();
    return vegaEmbed(el, spec, {{ actions: false, renderer: 'svg' }}).catch((e) => {{
      el.innerHTML = '<div style="color:#b91c1c;font-size:10pt">' + e + '</div>';
    }});
  }});
  Promise.all(promises).then(() => {{ window.__VEGA_READY__ = true; }});
</script>
</body>
</html>
"""


# ─── Embed resolver ─────────────────────────────────────────────────────

import re as _re

_EMBED_RX = _re.compile(r"!\[\[([a-zA-Z0-9_\-]+)\]\]")


def _resolve_embeds(md_text: str, slug: str | None) -> tuple[str, dict[str, dict]]:
    """Replace `![[chart_or_artifact_id]]` with chart tiles + collect specs."""
    specs: dict[str, dict] = {}

    if slug is None:
        return md_text, specs
    charts = {c["id"]: c for c in ws.list_charts(slug)}
    artifacts = {a["id"]: a for a in ws.list_artifacts(slug)}

    def _replace(m: _re.Match) -> str:
        key = m.group(1)
        # First-class chart match (full id or prefix).
        chart = charts.get(key) or next((c for c in charts.values() if c["id"].startswith(key)), None)
        if chart:
            # Prefer PNG when chart_png.py rendered it — Chrome inlines the
            # img directly, no Vega-Lite JS round-trip needed at print time.
            png_path = chart.get("png_path") or (chart.get("spec") or {}).get("png_path")
            if png_path and Path(png_path).exists():
                # file:// URI so Chrome can read it from disk during --print-to-pdf.
                file_uri = "file://" + str(Path(png_path).resolve())
                return (
                    f'<div class="chart-tile">'
                    f'<header><h4>{html.escape(chart.get("title", "Chart"))}</h4>'
                    f'<span class="kind">{html.escape(chart.get("kind", "chart"))}</span></header>'
                    f'<img src="{file_uri}" alt="{html.escape(chart.get("title", "Chart"))}" '
                    f'style="display:block;width:100%;height:auto;" />'
                    f"</div>"
                )
            specs[chart["id"]] = chart["spec"]
            return (
                f'<div class="chart-tile">'
                f'<header><h4>{html.escape(chart.get("title", "Chart"))}</h4>'
                f'<span class="kind">{html.escape(chart.get("kind", "chart"))}</span></header>'
                f'<div class="vega" id="vega-{chart["id"]}"></div>'
                f"</div>"
            )
        # Artifact match — render a metadata block (no rows).
        art = artifacts.get(key) or next((a for a in artifacts.values() if a["id"].startswith(key)), None)
        if art:
            return (
                f'<div class="chart-tile"><header>'
                f'<h4>{html.escape(art.get("title", "Artifact"))}</h4>'
                f'<span class="kind">artifact</span></header>'
                f'<div class="kvp"><b>question:</b> {html.escape(art.get("question", ""))}</div>'
                f'<div class="kvp"><b>rows:</b> {art.get("row_count", 0)}  · '
                f'<b>columns:</b> {", ".join(art.get("columns", []))}</div>'
                f'<pre><code>{html.escape(art.get("sql", ""))}</code></pre>'
                f'</div>'
            )
        # Unresolved — leave the placeholder visible so the writer notices.
        return f"`!![[unresolved:{html.escape(key)}]]!!`"

    return _EMBED_RX.sub(_replace, md_text), specs


# ─── Cover + body ───────────────────────────────────────────────────────

def _cover(title: str, subtitle: str = "", author: str = "") -> str:
    return (
        '<section class="cover">'
        '<div>'
        f'<div class="eyebrow">Data Analysis · Report</div>'
        '<div class="accent"></div>'
        f'<div class="title">{html.escape(title)}</div>'
        + (f'<p style="font-size:13pt;color:#444">{html.escape(subtitle)}</p>' if subtitle else "")
        + '</div>'
        '<div class="meta">'
        + (f'Author: {html.escape(author)}<br/>' if author else "")
        + f'Generated: {ws.now()}'
        '</div>'
        '</section>'
    )


def _render_html(md_text: str, *, title: str, slug: str | None, cover: bool, subtitle: str, author: str) -> str:
    body_md, specs = _resolve_embeds(md_text, slug)
    body_html = _md.markdown(
        body_md,
        extensions=["extra", "fenced_code", "tables", "codehilite", "toc"],
        extension_configs={"codehilite": {"guess_lang": False}},
    )
    cover_html = _cover(title, subtitle, author) if cover else ""
    return _HTML_TEMPLATE.format(
        title=html.escape(title),
        css=_PAGE_CSS,
        body=cover_html + '<main>' + body_html + '</main>',
        specs_json=json.dumps(specs),
    )


def _html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = _find_chrome()
    # Wait for Vega rendering before printing.
    subprocess.check_call([
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-sandbox",
        "--virtual-time-budget=8000",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        f"file://{html_path}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ─── Auto-generate digest from a project ────────────────────────────────

def _auto_digest_md(slug: str) -> str:
    proj = ws.require_project(slug)
    datasets = ws.list_datasets(slug)
    artifacts = ws.list_artifacts(slug)
    charts = ws.list_charts(slug)
    traces = ws.list_traces(slug)

    lines: list[str] = []
    lines.append(f"# {proj['name']}")
    if proj.get("description"):
        lines.append(f"> {proj['description']}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Slug: `{proj['slug']}`")
    lines.append(f"- Created: `{proj['created_at']}`")
    lines.append(f"- Last updated: `{proj['updated_at']}`")
    lines.append(f"- Datasets: **{len(datasets)}** · Artifacts: **{len(artifacts)}** · "
                 f"Charts: **{len(charts)}** · Traces: **{len(traces)}**")
    lines.append("")

    if datasets:
        lines.append("## Datasets")
        lines.append("")
        lines.append("| Name | Rows | Columns | Source |")
        lines.append("|---|---:|---:|---|")
        for d in datasets:
            lines.append(f"| `{d['name']}` | {d.get('rows', 0):,} | {len(d.get('columns', []))} | "
                         f"`{d.get('source_filename', '')}` |")
        lines.append("")

    if artifacts:
        lines.append("## Artifacts (knowledge memory)")
        for a in artifacts:
            lines.append(f"### {a.get('title', '(untitled)')}")
            if a.get("question"):
                lines.append(f"> {a['question']}")
            lines.append(f"`{a['row_count']}` rows · columns: {', '.join('`' + c + '`' for c in a.get('columns', []))}")
            lines.append("")
            lines.append("```sql")
            lines.append(a.get("sql", "").strip())
            lines.append("```")
            lines.append("")

    if charts:
        lines.append("## Charts")
        for c in charts:
            lines.append(f"![[{c['id']}]]")
            lines.append("")

    if traces:
        lines.append("## Execution traces")
        for t in traces:
            lines.append(f"- **{html.escape(t['query'])}** — "
                         f"tools: `{', '.join(t.get('tools_used', []))}` · "
                         f"{html.escape(t.get('result_summary', ''))}  "
                         f"<br/><sub>{t['created_at']}</sub>")
        lines.append("")

    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────

def cmd_render(args: argparse.Namespace) -> int:
    src = Path(args.md).expanduser()
    if not src.exists():
        print(f"ERROR: markdown not found: {src}", file=sys.stderr)
        return 1
    md_text = src.read_text(encoding="utf-8")
    title = args.title or src.stem.replace("_", " ").replace("-", " ").title()
    html_doc = _render_html(
        md_text, title=title, slug=args.slug,
        cover=not args.no_cover, subtitle=args.subtitle or "", author=args.author or "",
    )

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html_doc)
        tmp_path = Path(tmp.name)
    try:
        _html_to_pdf(tmp_path, out)
    finally:
        tmp_path.unlink(missing_ok=True)
    size_kb = out.stat().st_size / 1024
    print(json.dumps({"pdf": str(out), "size_kb": round(size_kb, 1), "title": title}, ensure_ascii=False))
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    md_text = _auto_digest_md(args.slug)
    if args.md_out:
        Path(args.md_out).expanduser().write_text(md_text, encoding="utf-8")
        print(f"md: {args.md_out}")
    proj = ws.require_project(args.slug)
    title = args.title or f"{proj['name']} · Digest"

    html_doc = _render_html(
        md_text, title=title, slug=args.slug,
        cover=not args.no_cover, subtitle=args.subtitle or "Auto-generated project digest",
        author=args.author or "",
    )
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as tmp:
        tmp.write(html_doc)
        tmp_path = Path(tmp.name)
    try:
        _html_to_pdf(tmp_path, out)
    finally:
        tmp_path.unlink(missing_ok=True)
    size_kb = out.stat().st_size / 1024
    print(json.dumps({"pdf": str(out), "size_kb": round(size_kb, 1),
                      "title": title, "charts_embedded": len(ws.list_charts(args.slug))},
                     ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Markdown → PDF report builder.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_r = sub.add_parser("render", help="render a .md file (with optional ![[id]] embeds) to PDF")
    p_r.add_argument("--md", required=True, help=".md source file")
    p_r.add_argument("--out", required=True, help="output PDF path")
    p_r.add_argument("--slug", help="resolve ![[id]] embeds against this project's charts/artifacts")
    p_r.add_argument("--title")
    p_r.add_argument("--subtitle")
    p_r.add_argument("--author")
    p_r.add_argument("--no-cover", action="store_true")
    p_r.set_defaults(fn=cmd_render)

    p_g = sub.add_parser("generate", help="auto-generate a project digest PDF (datasets + artifacts + charts + traces)")
    p_g.add_argument("--slug", required=True)
    p_g.add_argument("--out", required=True)
    p_g.add_argument("--md-out", help="also save the intermediate markdown to this path")
    p_g.add_argument("--title")
    p_g.add_argument("--subtitle")
    p_g.add_argument("--author")
    p_g.add_argument("--no-cover", action="store_true")
    p_g.set_defaults(fn=cmd_generate)

    args = parser.parse_args(argv[1:])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
