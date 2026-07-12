import pytest

from atria.core.blackboard.models import Task
from atria.core.blackboard.task_store import TaskStore
from atria.core.tasks.tasks import _claim_and_load


@pytest.mark.asyncio
async def test_claim_and_load_returns_task_once():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    store = TaskStore(redis, run_id="sa_x", ttl=60)
    await store.add([Task("t0", "solver", "do the thing")])

    first = await _claim_and_load(redis, "sa_x", "t0", 60)
    assert first is not None and first.prompt == "do the thing"
    # Redelivery: already claimed → None (worker skips duplicate execution).
    assert await _claim_and_load(redis, "sa_x", "t0", 60) is None


@pytest.mark.asyncio
async def test_claim_and_load_missing_task_is_none():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    assert await _claim_and_load(redis, "sa_x", "nope", 60) is None
