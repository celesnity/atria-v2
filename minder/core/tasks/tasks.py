"""The background-subagent TaskIQ task. Runs in the worker process."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from minder.core.agents.deps_builder import build_runtime_and_deps
from minder.core.blackboard.task_store import TaskStore
from minder.core.tasks.broker import broker
from minder.core.tasks.payload import SubagentTaskPayload

logger = logging.getLogger(__name__)


def _run_subagent_sync(runtime_suite: Any, deps: Any, payload: SubagentTaskPayload) -> dict:
    """Run the subagent synchronously via the manager.

    Blocking; called inside asyncio.to_thread so the worker's event loop stays
    responsive. Fire-and-collect: returns the final result dict only.
    """
    manager = runtime_suite.tool_registry.get_subagent_manager()
    if manager is None:
        return {
            "success": False,
            "content": "no subagent manager available in worker runtime",
            "messages": [],
            "completion_status": "error",
        }
    result = manager.execute_subagent(
        name=payload.subagent_type,
        task=payload.prompt,
        deps=deps,
        show_spawn_header=False,
        tool_call_id=payload.parent_tool_call_id,
        working_dir=payload.working_dir,
        path_mapping=payload.path_mapping or None,
    )
    return {
        "success": bool(result.get("success")),
        "content": result.get("content", ""),
        "messages": result.get("messages", []),
        "completion_status": result.get("completion_status", "success"),
    }


async def _write_response(
    redis: Any, run_id: str, responder: str, content: str, confidence: float
) -> None:
    """Write one helper answer to the response board β_r (best-effort)."""
    import time

    from minder.core.blackboard.models import Response
    from minder.core.blackboard.response_store import ResponseStore

    store = ResponseStore(redis, run_id=run_id, ttl=3600)
    await store.add([Response(request_id=run_id, responder=responder,
                              content=content[:1000], confidence=confidence, ts=time.time())])
    try:
        from minder.core.blackboard.board_events import publish_board_event

        await publish_board_event(redis, run_id, "response", {
            "request_id": run_id, "responder": responder,
            "content": content[:1000], "confidence": confidence,
        })
    except Exception:  # noqa: BLE001 — viewer event is best-effort
        pass


async def _claim_and_load(redis: Any, bb_id: str, task_id: str, ttl: int):
    """Claim ``task_id`` on the blackboard and return its Task, or None.

    Returns None when the task is missing or already claimed (at-least-once
    redelivery) so the worker never runs the same delegated task twice.
    """
    store = TaskStore(redis, run_id=bb_id, ttl=ttl)
    if not await store.claim(task_id):
        return None
    return await store.get(task_id)


@broker.task(task_name="minder.core.tasks.tasks.run_background_subagent")
async def run_background_subagent(payload: dict) -> dict:
    """Rebuild a headless runtime from the payload and run the subagent.

    When the payload names a ``subagent_task_id`` the task is read from the
    blackboard (the source of task), claimed to guard against redelivery, and its
    final status is written back to the blackboard task channel.
    """
    p = SubagentTaskPayload.model_validate(payload)
    deps: Any = None
    redis: Any = None
    task_store: Any = None
    if p.subagent_task_id and p.blackboard_task_id:
        import redis.asyncio as aioredis

        url = os.environ.get("MINDER_REDIS_URL", "redis://localhost:6379/0")
        redis = aioredis.from_url(url)
        claimed = await _claim_and_load(redis, p.blackboard_task_id, p.subagent_task_id, 3600)
        if claimed is None:
            await redis.aclose()
            return {
                "success": True,
                "content": "skipped (already claimed)",
                "messages": [],
                "completion_status": "skipped",
            }
        p.subagent_type = claimed.subagent_type
        p.prompt = claimed.prompt
        task_store = TaskStore(redis, run_id=p.blackboard_task_id, ttl=3600)
    try:
        runtime_suite, deps = build_runtime_and_deps(p)
        result = await asyncio.to_thread(_run_subagent_sync, runtime_suite, deps, p)
        if task_store is not None:
            status = "done" if result.get("success") else "failed"
            await task_store.set_status(
                p.subagent_task_id, status, result=str(result.get("content", ""))[:280]
            )
            if status == "done":
                await _write_response(
                    redis, p.blackboard_task_id, p.subagent_type,
                    str(result.get("content", "")), p.bid_confidence,
                )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("background subagent failed: %s", exc)
        if task_store is not None:
            await task_store.set_status(p.subagent_task_id, "failed", result=str(exc)[:280])
        return {
            "success": False,
            "content": f"background subagent failed: {exc}",
            "messages": [],
            "completion_status": "error",
        }
    finally:
        handle = getattr(deps, "blackboard", None) if deps is not None else None
        if handle is not None:
            from minder.core.blackboard.provision import teardown_run_blackboard

            teardown_run_blackboard(handle)
        if redis is not None:
            await redis.aclose()
