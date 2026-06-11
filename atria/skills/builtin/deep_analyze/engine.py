"""DeepAnalyzeEngine — holds job registry + LLM client + ctx."""

from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path
from typing import Any, Dict

from atria.core.skill_tools import SkillToolContext

from .jobs import AnalyzeJob, AnalyzeJobRegistry
from .pipeline import run_job
from .planning import run_planning
from .validation import validate_input


class DeepAnalyzeEngine:
    def __init__(self, ctx: SkillToolContext) -> None:
        self._ctx = ctx
        self._registry = AnalyzeJobRegistry()
        self._fallback_root = Path.home() / ".atria" / "sessions"

    def _job_root(self, session_id: str) -> Path:
        # Prefer the conversation workspace so artifacts.scan picks up charts +
        # data.db and the viewer can resolve them as relative payload_refs.
        # Fall back to the session-scoped legacy path only when no workspace
        # is wired (e.g. CLI/TUI without working_dir).
        wd = self._ctx.working_dir
        if wd:
            return Path(wd) / "analyze"
        return self._fallback_root / session_id / "analyze"

    def _client(self):
        from openai import OpenAI  # noqa: PLC0415

        return OpenAI(
            api_key=os.environ.get("DEEP_RESEARCH_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("DEEP_RESEARCH_BASE_URL", "https://api.openai.com/v1"),
        )

    def _chat(self, system: str, user: str) -> str:
        if self._ctx.llm_chat is not None:
            return self._ctx.llm_chat(system, user)
        resp = self._client().chat.completions.create(
            model=os.environ.get("DEEP_RESEARCH_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    def _vision_insight(self, png_path: str) -> str:
        with open(png_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        system = (
            "You are a data-analysis assistant. Describe the chart, the "
            "takeaway, and any anomalies, in 3-6 sentences of markdown."
        )
        user_text = "Analyze this chart:"
        if self._ctx.llm_vision is not None:
            return self._ctx.llm_vision(system, user_text, b64)
        resp = self._client().chat.completions.create(
            model=os.environ.get("DEEP_RESEARCH_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    def deep_analyze(self, file_path: str, session_id: str = "default") -> Dict[str, Any]:
        try:
            validated = validate_input(file_path)
            job_id = uuid.uuid4().hex[:12]
            job_dir = self._job_root(session_id) / job_id
            (job_dir / "charts").mkdir(parents=True, exist_ok=True)
            job = AnalyzeJob(
                job_id=job_id, session_id=session_id,
                file_path=str(validated), dir=job_dir,
            )

            def planner(profile):
                return run_planning(profile, chat=self._chat)

            dispatcher = self._ctx.subagent_dispatcher

            def extractor(job_, spec):
                if dispatcher is None:
                    return
                dispatcher(
                    agent="Data-Extractor",
                    task=(
                        f"Materialize sub-table `{spec['name']}` in the SQLite DB at "
                        f"{job_.dir / 'data.db'}. Planner SQL:\n\n{spec['sql']}\n\n"
                        f"Goal: {spec.get('why', '')}"
                    ),
                )

            def visualizer(job_, spec):
                if dispatcher is None:
                    return
                png = str(job_.dir / "charts" / f"{spec['name']}.png")
                dispatcher(
                    agent="Visualizer",
                    task=(
                        f"Render chart `{spec['name']}` from the SQLite DB at "
                        f"{job_.dir / 'data.db'}, table `{spec['source_table']}`. "
                        f"Spec: type={spec['type']}, x={spec['x']}, y={spec['y']}, "
                        f"title={spec['title']!r}. Output PNG: {png}."
                    ),
                )

            def insighter(_job, png_path):
                return self._vision_insight(png_path)

            self._registry.submit(
                job,
                lambda j: run_job(
                    self._ctx, self._registry, j,
                    planner=planner, extractor=extractor,
                    visualizer=visualizer, insighter=insighter,
                    reporter=None,
                ),
            )
            if self._ctx.broadcaster:
                self._ctx.broadcaster(
                    {"type": "analyze.started", "job_id": job_id, "file_name": validated.name}
                )
            bg_summary = (
                f"Deep analyze started on `{validated.name}` (job `{job_id}`). "
                "Poll `get_analyze_status(job_id=...)` for progress; charts and the "
                "final PDF stream to chat as they complete."
            )
            return {
                "success": True,
                "output": bg_summary,
                "job_id": job_id,
                "_bg_task_started": True,
                "_bg_summary": bg_summary,
                "error": None,
            }
        except Exception as e:
            return {"success": False, "output": str(e), "error": str(e)}

    def get_analyze_status(self, job_id: str) -> Dict[str, Any]:
        job = self._registry.get(job_id)
        if job is None:
            return {"success": False, "output": "unknown job_id", "error": "unknown job_id"}
        details = {
            "status": job.status,
            "sub_tables": job.sub_tables,
            "charts": [
                {"name": c["name"], "png_path": c["png_path"], "insight_md": c["insight_md"]}
                for c in job.charts
            ],
            "report_path": job.report_path,
            "error": job.error,
        }
        summary = (
            f"job {job_id}: status={job.status}, "
            f"sub_tables={len(job.sub_tables)}, charts={len(job.charts)}"
            + (f", report={job.report_path}" if job.report_path else "")
            + (f", error={job.error}" if job.error else "")
        )
        return {
            "success": True,
            "output": summary,
            "details": details,
            "error": None,
        }

    def cancel_analyze(self, job_id: str) -> Dict[str, Any]:
        job = self._registry.get(job_id)
        ok = False
        if job is not None and job.status not in {"done", "failed", "cancelled"}:
            job.cancel_event.set()
            ok = True
        return {
            "success": True,
            "output": f"cancelled={ok}",
            "cancelled": ok,
            "error": None,
        }
