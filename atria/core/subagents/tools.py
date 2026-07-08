"""Tool handlers + orchestrator builder for the unified ``subagent`` tool.

Mirrors the old divide/parallel tool builders but without decomposition, DAG
scheduling, or candidate judging. ``subagent`` writes flat tasks to the
blackboard and fans one worker out per task; ``get_subagent_output`` collects.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from atria.core.orchestration.bridge import ensure_async_redis, make_run_async
from atria.core.orchestration.job_store import SUBAGENT_PREFIX, JobStore
from atria.core.subagents.orchestrator import SubagentOrchestrator
from atria.core.tasks.payload import SubagentTaskPayload

logger = logging.getLogger(__name__)


def build_subagent_orchestrator(
    task_client: Any,
    config: Any,
    owner_id: str,
    session_id: str,
    working_dir: str = "",
    progress_cb: Any = None,
    redis_client: Any = None,
) -> SubagentOrchestrator:
    """Construct a SubagentOrchestrator that fans workers over the task broker."""
    sub_cfg = getattr(config, "divide", None) or config
    run_async = make_run_async(task_client)
    redis_client = ensure_async_redis(
        redis_client, getattr(sub_cfg, "redis_url", "redis://localhost:6379/0")
    )
    broker = task_client._broker

    async def enqueue_worker(payload: SubagentTaskPayload) -> str:
        from atria.core.tasks import meta
        from atria.core.tasks.client import _TASK_NAME

        task = broker.find_task(_TASK_NAME)
        if task is None:
            raise RuntimeError(f"task {_TASK_NAME} not registered")
        kicked = await task.kiq(payload.model_dump())
        await meta.record_enqueue(redis_client, kicked.task_id, payload.session_id)
        return kicked.task_id

    async def await_worker(task_ids: list[str]) -> tuple[str, dict]:
        backend = broker.result_backend
        while True:
            for tid in task_ids:
                if await backend.is_result_ready(tid):
                    res = await backend.get_result(tid, with_logs=False)
                    if res.is_err:
                        return tid, {"status": "failed", "error": str(res.error)}
                    return tid, {**(res.return_value or {}), "status": "done"}
            await asyncio.sleep(0.25)

    return SubagentOrchestrator(
        job_store=JobStore(redis_client, SUBAGENT_PREFIX),
        redis_client=redis_client,
        config=sub_cfg,
        run_async=run_async,
        enqueue_worker=enqueue_worker,
        await_worker=await_worker,
        owner_id=owner_id,
        session_id=session_id,
        working_dir=working_dir,
        progress_cb=progress_cb,
    )


def execute_subagent_fanout(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Write tasks to the blackboard and fan workers out. Returns a job handle."""
    tasks = arguments.get("tasks")
    if not tasks or not isinstance(tasks, list):
        return {"success": False, "error": "tasks (non-empty list) is required", "output": None}
    try:
        job_id = orchestrator.start(tasks)
    except Exception as exc:  # noqa: BLE001 — surface as tool error, never crash the loop
        logger.warning("subagent fan-out start failed: %s", exc)
        return {"success": False, "error": f"subagent failed: {exc}", "output": None}
    return {
        "success": True,
        "job_id": job_id,
        "status": "running",
        "output": (
            f"[SUBAGENT STARTED] job_id={job_id} with {len(tasks)} task(s). "
            "Use get_subagent_output(job_id) to poll and collect results."
        ),
    }


def execute_get_subagent_output(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Collect task statuses + the shared-context notes digest for a job."""
    job_id = arguments.get("job_id", "")
    if not job_id:
        return {"success": False, "error": "job_id is required", "output": None}
    try:
        result = orchestrator.collect(
            job_id,
            block=arguments.get("block", True),
            timeout_ms=arguments.get("timeout", 30000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_subagent_output failed: %s", exc)
        return {"success": False, "error": f"get_subagent_output failed: {exc}", "output": None}
    return {"success": result.get("status") != "unknown", "output": result}
