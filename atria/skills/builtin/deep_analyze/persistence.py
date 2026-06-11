"""Default markdown -> PDF report builder for deep_analyze."""

from __future__ import annotations

from pathlib import Path
from typing import List

from .jobs import AnalyzeJob


def default_reporter(job: AnalyzeJob) -> str:
    from atria.core.context_engineering.tools.implementations.md_to_pdf_tool import MdToPdfTool

    md_lines: List[str] = [f"# Analyze Report — {Path(job.file_path).name}\n"]
    md_lines.append(f"_{job.plan.get('summary', '')}_\n")
    for chart in job.charts:
        if chart["status"] != "done":
            md_lines.append(f"## {chart['name']} (failed)\n")
            md_lines.append(f"`{chart.get('error', 'unknown error')}`\n")
            continue
        md_lines.append(f"## {chart['name']}\n")
        md_lines.append(f"![{chart['name']}]({chart['png_path']})\n")
        if chart.get("insight_md"):
            md_lines.append(chart["insight_md"] + "\n")
    md_path = job.dir / "report.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    pdf_path = str(job.dir / "report.pdf")
    res = MdToPdfTool().render(str(md_path), pdf_path)
    if not res["success"]:
        raise RuntimeError(res["error"])
    return pdf_path
