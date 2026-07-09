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
    helper_profiles: list[tuple[str, str]] | None = None,
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

    from atria.core.blackboard.verify_llm import build_verify_llm

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
        helper_profiles=helper_profiles or [],
        verify_llm=build_verify_llm(config),
    )


def execute_request_help(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Post an un-addressed help request; return a request handle."""
    prompt = arguments.get("prompt")
    if not prompt or not isinstance(prompt, str):
        return {"success": False, "error": "prompt (string) is required", "output": None}
    max_helpers = int(arguments.get("max_helpers", 3) or 3)
    try:
        request_id = orchestrator.start(prompt, max_helpers=max_helpers)
    except Exception as exc:  # noqa: BLE001 — surface as tool error, never crash the loop
        logger.warning("request_help start failed: %s", exc)
        return {"success": False, "error": f"request_help failed: {exc}", "output": None}
    return {
        "success": True,
        "request_id": request_id,
        "status": "running",
        "output": (
            f"[REQUEST POSTED] request_id={request_id}. Helpers are bidding; use "
            "get_help_responses(request_id) to collect volunteers' answers."
        ),
    }


def execute_get_help_responses(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Collect response-board answers + bid roster + note digest for a request."""
    request_id = arguments.get("request_id", "")
    if not request_id:
        return {"success": False, "error": "request_id is required", "output": None}
    try:
        result = orchestrator.collect(request_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_help_responses failed: %s", exc)
        return {"success": False, "error": f"get_help_responses failed: {exc}", "output": None}
    return {"success": result.get("status") != "unknown", "output": result}
