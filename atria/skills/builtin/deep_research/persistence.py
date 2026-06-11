"""Save completed research report as markdown."""

from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

from .jobs import ResearchJob

logger = logging.getLogger(__name__)


def save_report(job: ResearchJob, working_dir: Optional[str]) -> str:
    slug = re.sub(r"[^\w\s-]", "", job.topic.lower()).strip()
    slug = re.sub(r"[\s]+", "_", slug)[:40]
    filename = f"research_{slug}_{job.job_id[:6]}.md"

    base = working_dir or os.getcwd()
    filepath = os.path.join(base, filename)

    lines: List[str] = [f"# Research Report: {job.topic}\n"]
    current_cat: Optional[str] = None
    for section in job.report_sections:
        if section["category"] != current_cat:
            current_cat = section["category"]
            lines.append(f"\n## {current_cat}\n")
        lines.append(section["content"])
        lines.append("")

    try:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        logger.info(f"Research report saved: {filepath}")
    except Exception as exc:
        logger.error(f"Failed to save research report: {exc}")
        filepath = ""
    return filepath
