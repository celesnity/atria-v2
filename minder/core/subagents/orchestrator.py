"""Broadcast-request orchestrator (paper arXiv:2510.01285): write an un-addressed
request, run an autonomous per-helper bid, enqueue the existing worker path for
volunteers only, and collect responses (β_r) + the bid roster + note digest."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable

from minder.core.blackboard.models import Bid, Request, Task
from minder.core.blackboard.render import render_digest
from minder.core.blackboard.response_store import BidStore, ResponseStore
from minder.core.blackboard.store import BlackboardStore
from minder.core.blackboard.task_store import TaskStore
from minder.core.orchestration.job_store import JobStore
from minder.core.subagents.bid import run_bids
from minder.core.tasks.payload import SubagentTaskPayload

logger = logging.getLogger(__name__)


class SubagentOrchestrator:
    """Run one broadcast request: request → bid → enqueue volunteers → collect."""

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
        helper_profiles: list[tuple[str, str]] | None = None,
        verify_llm: Callable[[str, str], str] | None = None,
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
        self._profiles = helper_profiles or []
        self._verify_llm = verify_llm

    def _emit(self, stage: str, data: dict) -> None:
        if self._cb is None:
            return
        try:
            self._cb(stage, data)
        except Exception as exc:  # noqa: BLE001 — telemetry never breaks the job
            logger.warning("subagent progress_cb failed at %s: %s", stage, exc)

    async def _publish(self, run_id: str, kind: str, payload: dict) -> None:
        try:
            from minder.core.blackboard.board_events import publish_board_event

            await publish_board_event(self._redis, run_id, kind, payload)
        except Exception as exc:  # noqa: BLE001 — viewer events never break the job
            logger.warning("board event publish failed (%s): %s", kind, exc)

    def start(self, prompt: str, max_helpers: int = 3) -> str:
        return self._run_async(self.start_async(prompt, max_helpers))

    def collect(self, job_id: str, block: bool = True, timeout_ms: int = 30000) -> dict:
        return self._run_async(self.collect_async(job_id))

    async def start_async(self, prompt: str, max_helpers: int = 3) -> str:
        """Post a request, bid it out, enqueue volunteers, return the job/request id."""
        job_id = uuid.uuid4().hex[:12]
        bb_id = "sa_" + job_id
        now = time.time()

        request = Request(id=bb_id, prompt=prompt, status="open", ts=now)
        await self._publish(bb_id, "request", request.to_dict())

        bids = await run_bids(bb_id, prompt, self._profiles, self._verify_llm,
                              max_helpers=max_helpers, now=now)
        await BidStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl).add(bids)
        for b in bids:
            await self._publish(bb_id, "bid", b.to_dict())

        volunteers = [b for b in bids if b.volunteered]
        task_objs = [
            Task(id=f"t{i}", subagent_type=b.responder, prompt=prompt, ts=now)
            for i, b in enumerate(volunteers)
        ]
        if task_objs:
            await TaskStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl).add(task_objs)

        record = {
            "job_id": job_id,
            "bb_id": bb_id,
            "task_ids": [t.id for t in task_objs],
            "status": "running" if task_objs else "done",
        }
        await self._js.save(job_id, record, ttl=self._cfg.pjob_ttl)
        self._emit("started", {
            "job_id": job_id,
            "request": prompt,
            "bids": [b.to_dict() for b in bids],
        })

        if not task_objs:
            self._emit("done", {"job_id": job_id, "status": "done"})
            return job_id

        enqueued: list[str] = []
        for i, (t, b) in enumerate(zip(task_objs, volunteers)):
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
                bid_confidence=b.confidence,
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
            return {"status": "unknown", "error": f"no such job {job_id}",
                    "responses": [], "bids": [], "digest": ""}
        bb_id = rec["bb_id"]
        ttl = self._cfg.pjob_ttl
        responses = await ResponseStore(self._redis, run_id=bb_id, ttl=ttl).all()
        bids = await BidStore(self._redis, run_id=bb_id, ttl=ttl).all()
        notes = await BlackboardStore(self._redis, task_id=bb_id, ttl=ttl).read_all()
        return {
            "status": rec.get("status", "running"),
            "responses": [r.to_dict() for r in
                          sorted(responses, key=lambda x: -x.confidence)],
            "bids": [b.to_dict() for b in bids],
            "digest": render_digest(notes, viewer_id=0, window_tokens=2000),
        }
