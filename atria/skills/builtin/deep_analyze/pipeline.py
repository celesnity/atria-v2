"""Background analyze pipeline."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from atria.core.skill_tools import SkillToolContext

from .dataloader import load_to_sqlite, profile_schema
from .jobs import AnalyzeJob, AnalyzeJobRegistry
from .persistence import default_reporter

logger = logging.getLogger(__name__)

PlannerFn = Callable[[Dict[str, Any]], Dict[str, Any]]
ExtractorFn = Callable[[AnalyzeJob, Dict[str, Any]], None]
VisualizerFn = Callable[[AnalyzeJob, Dict[str, Any]], None]
InsighterFn = Callable[[AnalyzeJob, str], str]
ReporterFn = Callable[[AnalyzeJob], str]


def _emit(ctx: SkillToolContext, event: Dict[str, Any]) -> None:
    if ctx.broadcaster is None:
        return
    try:
        ctx.broadcaster(event)
    except Exception as e:
        logger.warning("progress callback failed: %s", e)


def _check_cancel(ctx: SkillToolContext, job: AnalyzeJob) -> bool:
    if job.cancel_event.is_set():
        job.status = "cancelled"
        _emit(ctx, {"type": "analyze.cancelled", "job_id": job.job_id})
        return True
    return False


def run_job(
    ctx: SkillToolContext,
    registry: AnalyzeJobRegistry,
    job: AnalyzeJob,
    planner: PlannerFn,
    extractor: ExtractorFn,
    visualizer: VisualizerFn,
    insighter: InsighterFn,
    reporter: Optional[ReporterFn] = None,
) -> None:
    try:
        job.status = "loading"
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "load", "status": "start"})
        rows = load_to_sqlite(Path(job.file_path), job.dir / "data.db")
        job.profile = profile_schema(job.dir / "data.db", file_name=Path(job.file_path).name)
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "load",
                    "status": "done", "rows": rows, "cols": len(job.profile["columns"])})
        if _check_cancel(ctx, job):
            return

        job.status = "planning"
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "plan", "status": "start"})
        job.plan = planner(job.profile)
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "plan",
                    "status": "done", "sub_tables": len(job.plan["sub_tables"]),
                    "charts": len(job.plan["charts"])})
        if _check_cancel(ctx, job):
            return

        job.status = "extracting"
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "extract", "status": "start"})
        job.sub_tables = _fanout_extract(ctx, registry, job, extractor)
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "extract", "status": "done"})
        if _check_cancel(ctx, job):
            return

        successful = {s["name"] for s in job.sub_tables if s["status"] == "done"}
        renderable = [c for c in job.plan["charts"]
                      if c["source_table"].removeprefix("t_") in successful]

        job.status = "rendering"
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "render", "status": "start"})
        job.charts = _fanout_render(ctx, registry, job, renderable, visualizer)
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "render", "status": "done"})
        if _check_cancel(ctx, job):
            return

        job.status = "insight"
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "insight", "status": "start"})
        _fanout_insight(ctx, registry, job, insighter)
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "insight", "status": "done"})
        if _check_cancel(ctx, job):
            return

        job.status = "reporting"
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "report", "status": "start"})
        fn = reporter or default_reporter
        job.report_path = fn(job)
        _emit(ctx, {"type": "analyze.phase", "job_id": job.job_id, "phase": "report", "status": "done"})
        _emit(ctx, {"type": "analyze.report", "job_id": job.job_id, "pdf_path": job.report_path})

        job.status = "done"
        _emit(ctx, {"type": "analyze.done", "job_id": job.job_id})
    except Exception as e:
        logger.exception("deep_analyze job failed: %s", e)
        job.status = "failed"
        job.error = str(e)
        _emit(ctx, {"type": "analyze.failed", "job_id": job.job_id, "phase": job.status, "error": str(e)})
    finally:
        job._done_event.set()


def _fanout_extract(ctx, registry, job, extractor):
    results, futures = [], []
    for spec in job.plan["sub_tables"]:
        futures.append(registry.fanout.submit(_run_extract, job, spec, extractor))
    for spec, fut in zip(job.plan["sub_tables"], futures):
        try:
            rows = fut.result()
            results.append({"name": spec["name"], "rows": rows, "status": "done"})
            _emit(ctx, {"type": "analyze.subtable", "job_id": job.job_id,
                        "name": spec["name"], "rows": rows, "status": "done"})
        except Exception as e:
            logger.warning("subtable %s failed: %s", spec["name"], e)
            results.append({"name": spec["name"], "rows": 0, "status": "failed", "error": str(e)})
            _emit(ctx, {"type": "analyze.subtable", "job_id": job.job_id,
                        "name": spec["name"], "rows": 0, "status": "failed", "error": str(e)})
    return results


def _run_extract(job, spec, extractor):
    extractor(job, spec)
    with sqlite3.connect(job.dir / "data.db") as cx:
        try:
            cx.execute(spec["sql"])
        except sqlite3.Error:
            pass
        # `spec['name']` is normalized at plan-parse time, so it never has the
        # ``t_`` prefix — but guard against an upstream regression.
        bare = spec["name"][2:] if spec["name"].startswith("t_") else spec["name"]
        table = f"t_{bare}"
        return cx.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _fanout_render(ctx, registry, job, charts, visualizer):
    from atria.core.context_engineering.tools.implementations.chart_tool import ChartTool

    results, futures = [], []
    for spec in charts:
        futures.append(registry.fanout.submit(_run_render, job, spec, visualizer, ChartTool()))
    for spec, fut in zip(charts, futures):
        try:
            png = fut.result()
            results.append({"name": spec["name"], "png_path": png, "insight_md": None, "status": "done"})
            _emit(ctx, {"type": "analyze.chart", "job_id": job.job_id, "name": spec["name"],
                        "png_path": png, "status": "done"})
        except Exception as e:
            logger.warning("chart %s failed: %s", spec["name"], e)
            results.append({"name": spec["name"], "png_path": None, "insight_md": None,
                            "status": "failed", "error": str(e)})
            _emit(ctx, {"type": "analyze.chart", "job_id": job.job_id, "name": spec["name"],
                        "png_path": None, "status": "failed", "error": str(e)})
    return results


def _run_render(job, spec, visualizer, chart_tool):
    visualizer(job, spec)
    png = str(job.dir / "charts" / f"{spec['name']}.png")
    if not Path(png).exists():
        res = chart_tool.render(
            db_path=str(job.dir / "data.db"),
            source_table=spec["source_table"],
            chart_type=spec["type"],
            x=spec["x"], y=spec["y"], title=spec["title"],
            out_path=png, agg=spec.get("agg"),
        )
        if not res["success"]:
            raise RuntimeError(res["error"])
    return png


def _fanout_insight(ctx, registry, job, insighter):
    futures = []
    targets = [c for c in job.charts if c["status"] == "done"]
    for c in targets:
        futures.append(registry.fanout.submit(insighter, job, c["png_path"]))
    for c, fut in zip(targets, futures):
        try:
            md = fut.result()
            c["insight_md"] = md
            _emit(ctx, {"type": "analyze.insight", "job_id": job.job_id,
                        "name": c["name"], "md": md, "status": "done"})
        except Exception as e:
            logger.warning("insight %s failed: %s", c["name"], e)
            c["insight_md"] = None
            _emit(ctx, {"type": "analyze.insight", "job_id": job.job_id,
                        "name": c["name"], "md": None, "status": "failed", "error": str(e)})
