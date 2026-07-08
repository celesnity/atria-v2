"""Subagent fan-out coordinator: write tasks to the blackboard, enqueue one worker
per task, collect statuses + notes. Worker I/O is injected (decoupled from TaskIQ)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable

from atria.core.blackboard.models import Task
from atria.core.blackboard.render import render_digest
from atria.core.blackboard.store import BlackboardStore
from atria.core.blackboard.task_store import TaskStore
from atria.core.orchestration.job_store import JobStore
from atria.core.tasks.payload import SubagentTaskPayload

logger = logging.getLogger(__name__)


class SubagentOrchestrator:
    """Run one subagent fan-out job over the injected worker broker."""

    def __init__(
        self,
        job_store: JobStore,
        redis_client: Any,
        config: Any,
        run_async: Callable[[Any], Any],
        enqueue_worker: Callable[[SubagentTaskPayload], Awaitable[str]],
        await_worker: Callable[[list[str]], Awaitable[tuple[str, dict]]],
        owner_id: str,
        session_id: str,
        working_dir: str = "",
        progress_cb: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._js = job_store
        self._redis = redis_client
        self._cfg = config
        self._run_async = run_async
        self._enqueue = enqueue_worker
        self._await = await_worker
        self._owner = owner_id
        self._session = session_id
        self._working_dir = working_dir
        self._cb = progress_cb

    def _emit(self, stage: str, data: dict) -> None:
        if self._cb is None:
            return
        try:
            self._cb(stage, data)
        except Exception as exc:  # noqa: BLE001 — telemetry never breaks the job
            logger.warning("subagent progress_cb failed at %s: %s", stage, exc)

    def start(self, tasks: list[dict]) -> str:
        return self._run_async(self.start_async(tasks))

    def collect(self, job_id: str, block: bool = True, timeout_ms: int = 30000) -> dict:
        return self._run_async(self.collect_async(job_id))

    async def start_async(self, tasks: list[dict]) -> str:
        """Persist tasks to the blackboard, enqueue one worker each, return job_id."""
        job_id = uuid.uuid4().hex[:12]
        bb_id = "sa_" + job_id
        now = time.time()
        task_objs = [
            Task(
                id=f"t{i}",
                subagent_type=str(t.get("subagent_type") or "general-purpose"),
                prompt=str(t.get("prompt") or ""),
                ts=now,
            )
            for i, t in enumerate(tasks)
        ]
        store = TaskStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl)
        await store.add(task_objs)

        record = {
            "job_id": job_id,
            "bb_id": bb_id,
            "task_ids": [t.id for t in task_objs],
            "status": "running",
        }
        await self._js.save(job_id, record, ttl=self._cfg.pjob_ttl)
        self._emit(
            "started",
            {
                "job_id": job_id,
                "tasks": [{"id": t.id, "subagent_type": t.subagent_type} for t in task_objs],
            },
        )

        enqueued: list[str] = []
        for i, t in enumerate(task_objs):
            payload = SubagentTaskPayload(
                session_id=self._session,
                owner_id=self._owner,
                subagent_type=t.subagent_type,
                prompt=t.prompt,
                working_dir=self._working_dir,
                config_snapshot={},
                blackboard_task_id=bb_id,
                thread_id=i,
                subagent_task_id=t.id,
            )
            enqueued.append(await self._enqueue(payload))

        asyncio.create_task(self._await_all(job_id, record, enqueued))
        return job_id

    async def _await_all(self, job_id: str, record: dict, task_ids: list[str]) -> None:
        """Drain worker completions, then flip the job to done. Never re-raises."""
        try:
            pending = set(task_ids)
            while pending:
                tid, _ = await self._await(list(pending))
                pending.discard(tid)
            record["status"] = "done"
            await self._js.save(job_id, record, ttl=self._cfg.pjob_ttl)
            self._emit("done", {"job_id": job_id, "status": "done"})
        except Exception as exc:  # noqa: BLE001 — background task must not crash silently
            logger.exception("subagent workers crashed for %s: %s", job_id, exc)

    async def collect_async(self, job_id: str) -> dict:
        rec = await self._js.load(job_id)
        if rec is None:
            return {
                "status": "unknown",
                "error": f"no such job {job_id}",
                "tasks": [],
                "digest": "",
            }
        bb_id = rec["bb_id"]
        tasks = await TaskStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl).all()
        notes = await BlackboardStore(self._redis, task_id=bb_id, ttl=self._cfg.pjob_ttl).read_all()
        return {
            "status": rec.get("status", "running"),
            "tasks": [
                {"id": t.id, "subagent_type": t.subagent_type, "status": t.status}
                for t in sorted(tasks, key=lambda x: x.id)
            ],
            "digest": render_digest(notes, viewer_id=0, window_tokens=2000),
        }
