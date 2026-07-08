import asyncio

import pytest

from atria.core.blackboard.task_store import TaskStore
from atria.core.orchestration.job_store import JobStore, SUBAGENT_PREFIX
from atria.core.subagents.orchestrator import SubagentOrchestrator


class _Cfg:
    pjob_ttl = 60


def _make_orch(redis, enqueued):
    async def enqueue_worker(payload):
        enqueued.append(payload)
        return f"tk_{payload.subagent_task_id}"

    async def await_worker(task_ids):
        await asyncio.sleep(0)
        return task_ids[0], {"status": "done"}

    return SubagentOrchestrator(
        job_store=JobStore(redis, SUBAGENT_PREFIX),
        redis_client=redis,
        config=_Cfg(),
        run_async=lambda coro: asyncio.get_event_loop().run_until_complete(coro),
        enqueue_worker=enqueue_worker,
        await_worker=await_worker,
        owner_id="o",
        session_id="s",
    )


@pytest.mark.asyncio
async def test_start_writes_tasks_and_enqueues_one_worker_each():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    enqueued: list = []
    orch = _make_orch(redis, enqueued)
    job_id = await orch.start_async(
        [
            {"subagent_type": "code_explorer", "prompt": "a"},
            {"subagent_type": "solver", "prompt": "b"},
        ]
    )
    rec = await JobStore(redis, SUBAGENT_PREFIX).load(job_id)
    assert rec is not None and len(rec["task_ids"]) == 2
    assert len(enqueued) == 2
    assert {p.subagent_task_id for p in enqueued} == set(rec["task_ids"])
    store = TaskStore(redis, run_id=rec["bb_id"], ttl=60)
    assert {t.prompt for t in await store.all()} == {"a", "b"}


@pytest.mark.asyncio
async def test_collect_reports_task_statuses_and_digest():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    orch = _make_orch(redis, [])
    job_id = await orch.start_async([{"subagent_type": "solver", "prompt": "b"}])
    rec = await JobStore(redis, SUBAGENT_PREFIX).load(job_id)
    await TaskStore(redis, run_id=rec["bb_id"], ttl=60).set_status(
        rec["task_ids"][0], "done", result="ok"
    )
    out = await orch.collect_async(job_id)
    assert out["status"] in ("running", "done")
    assert out["tasks"][0]["status"] == "done"
    assert "digest" in out
