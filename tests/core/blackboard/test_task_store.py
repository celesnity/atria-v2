import pytest

from atria.core.blackboard.models import Task
from atria.core.blackboard.task_store import TaskStore


@pytest.mark.asyncio
async def test_add_get_all_roundtrip():
    from fakeredis import aioredis as fake_aioredis

    store = TaskStore(fake_aioredis.FakeRedis(), run_id="r1", ttl=60)
    await store.add([Task("t0", "solver", "a", ts=1.0), Task("t1", "code_explorer", "b", ts=2.0)])
    got = await store.get("t0")
    assert got is not None and got.subagent_type == "solver"
    ids = sorted(t.id for t in await store.all())
    assert ids == ["t0", "t1"]


@pytest.mark.asyncio
async def test_claim_is_exclusive_and_sets_status():
    from fakeredis import aioredis as fake_aioredis

    store = TaskStore(fake_aioredis.FakeRedis(), run_id="r2", ttl=60)
    await store.add([Task("t0", "solver", "a")])
    assert await store.claim("t0") is True
    assert await store.claim("t0") is False
    assert (await store.get("t0")).status == "claimed"


@pytest.mark.asyncio
async def test_set_status_updates_result():
    from fakeredis import aioredis as fake_aioredis

    store = TaskStore(fake_aioredis.FakeRedis(), run_id="r3", ttl=60)
    await store.add([Task("t0", "solver", "a")])
    await store.set_status("t0", "done", result="finished")
    got = await store.get("t0")
    assert got.status == "done" and got.result == "finished"
