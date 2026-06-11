"""Orchestrator: phase ordering, parallel fan-out, cancellation, failures."""

import sqlite3
import threading
import uuid
from pathlib import Path

import pytest

from atria.core.skill_tools import SkillToolContext
from atria.skills.builtin.deep_analyze.jobs import AnalyzeJob, AnalyzeJobRegistry
from atria.skills.builtin.deep_analyze.pipeline import run_job
from atria.skills.builtin.deep_analyze.planning import PlanningError


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    p = tmp_path / "sales.csv"
    p.write_text("region,r\nNA,100\nEU,80\nAPAC,200\n")
    return p


def _plan() -> dict:
    return {
        "summary": "s",
        "sub_tables": [
            {"name": "by_region",
             "sql": "CREATE TABLE t_by_region AS SELECT region, SUM(r) r FROM raw GROUP BY region",
             "why": ""},
        ],
        "charts": [
            {"name": "regional", "source_table": "t_by_region", "type": "bar",
             "x": "region", "y": ["r"], "title": "Regional", "why": ""},
        ],
    }


def _make_job(tmp_path: Path, session_id: str, csv_file: Path) -> AnalyzeJob:
    job_id = uuid.uuid4().hex[:12]
    job_dir = tmp_path / session_id / "analyze" / job_id
    (job_dir / "charts").mkdir(parents=True, exist_ok=True)
    return AnalyzeJob(
        job_id=job_id,
        session_id=session_id,
        file_path=str(csv_file),
        dir=job_dir,
    )


def _run_blocking(
    job: AnalyzeJob,
    registry: AnalyzeJobRegistry,
    ctx: SkillToolContext,
    *,
    planner,
    extractor=lambda job, spec: None,
    visualizer=lambda job, spec: None,
    insighter=lambda job, png: "insight",
    reporter=None,
    timeout: float = 30,
) -> None:
    registry.submit(
        job,
        lambda j: run_job(
            ctx, registry, j,
            planner=planner, extractor=extractor,
            visualizer=visualizer, insighter=insighter,
            reporter=reporter,
        ),
    )
    job._done_event.wait(timeout=timeout)


def test_happy_path(csv_file: Path, tmp_path: Path) -> None:
    events: list[dict] = []
    ctx = SkillToolContext(broadcaster=lambda e: events.append(e))
    registry = AnalyzeJobRegistry()
    job = _make_job(tmp_path, "s1", csv_file)

    _run_blocking(
        job, registry, ctx,
        planner=lambda profile: _plan(),
        reporter=lambda job: str(job.dir / "report.pdf"),
    )

    assert job.status == "done"
    phases = [e["phase"] for e in events
              if e.get("type") == "analyze.phase" and e.get("status") == "done"]
    assert phases == ["load", "plan", "extract", "render", "insight", "report"]
    with sqlite3.connect(job.dir / "data.db") as cx:
        assert cx.execute("SELECT COUNT(*) FROM t_by_region").fetchone()[0] == 3


def test_subtable_failure_does_not_abort_job(csv_file: Path, tmp_path: Path) -> None:
    bad_plan = _plan()
    bad_plan["sub_tables"].append(
        {"name": "broken", "sql": "CREATE TABLE t_broken AS SELECT nonsense FROM raw", "why": ""}
    )
    bad_plan["charts"].append(
        {"name": "broken_chart", "source_table": "t_broken", "type": "bar",
         "x": "region", "y": ["r"], "title": "x", "why": ""}
    )
    ctx = SkillToolContext()
    registry = AnalyzeJobRegistry()
    job = _make_job(tmp_path, "s2", csv_file)

    _run_blocking(
        job, registry, ctx,
        planner=lambda profile: bad_plan,
        reporter=lambda job: str(job.dir / "report.pdf"),
    )

    assert job.status == "done"
    assert any(s["status"] == "failed" for s in job.sub_tables)
    assert any(s["status"] == "done" for s in job.sub_tables)


def test_cancel_before_render(csv_file: Path, tmp_path: Path) -> None:
    gate = threading.Event()

    def slow_extractor(job, spec):
        gate.wait(timeout=5)

    ctx = SkillToolContext()
    registry = AnalyzeJobRegistry()
    job = _make_job(tmp_path, "s3", csv_file)
    registry.submit(
        job,
        lambda j: run_job(
            ctx, registry, j,
            planner=lambda profile: _plan(),
            extractor=slow_extractor,
            visualizer=lambda job, spec: None,
            insighter=lambda job, png: "ok",
            reporter=lambda job: "x",
        ),
    )
    job.cancel_event.set()
    gate.set()
    job._done_event.wait(timeout=10)
    assert job.status == "cancelled"


def test_empty_plan_marks_failed(csv_file: Path, tmp_path: Path) -> None:
    def empty_planner(_profile):
        raise PlanningError("planner produced no work")

    ctx = SkillToolContext()
    registry = AnalyzeJobRegistry()
    job = _make_job(tmp_path, "s4", csv_file)

    _run_blocking(
        job, registry, ctx,
        planner=empty_planner,
        reporter=lambda job: "x",
        timeout=10,
    )

    assert job.status == "failed"
    assert "no work" in (job.error or "")


@pytest.mark.skipif(
    True,
    reason="default reporter uses MdToPdfTool which requires pango/cairo native libs",
)
def test_default_reporter_produces_pdf(csv_file: Path, tmp_path: Path) -> None:
    ctx = SkillToolContext()
    registry = AnalyzeJobRegistry()
    job = _make_job(tmp_path, "s5", csv_file)
    _run_blocking(
        job, registry, ctx,
        planner=lambda profile: _plan(),
        insighter=lambda job, png: "insight",
        reporter=None,
    )
    assert job.status == "done"
    assert job.report_path and Path(job.report_path).exists()
    assert Path(job.report_path).read_bytes()[:4] == b"%PDF"
