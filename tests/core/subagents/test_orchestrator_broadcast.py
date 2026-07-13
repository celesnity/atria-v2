import pytest

from minder.core.subagents.orchestrator import SubagentOrchestrator


class FakeRedis:
    def __init__(self):
        self.h = {}
        self.published = []
    async def hset(self, key, mapping=None):
        self.h.setdefault(key, {}).update(mapping or {})
    async def hget(self, key, field):
        v = self.h.get(key, {}).get(field)
        return v.encode() if isinstance(v, str) else v
    async def hgetall(self, key):
        return {k.encode(): v.encode() for k, v in self.h.get(key, {}).items()}
    async def expire(self, key, ttl):
        return True
    async def set(self, key, val, nx=False, ex=None):
        return True
    async def publish(self, channel, payload):
        self.published.append((channel, payload))


class FakeJobStore:
    def __init__(self):
        self.saved = {}
    async def save(self, job_id, record, ttl):
        self.saved[job_id] = record
    async def load(self, job_id):
        return self.saved.get(job_id)


class Cfg:
    pjob_ttl = 60


def _orch(profiles, verify_llm, enqueued):
    async def enqueue(payload):
        enqueued.append(payload)
        return "kick_" + (payload.subagent_task_id or "?")

    async def await_worker(ids):
        return ids[0], {"status": "done"}

    return SubagentOrchestrator(
        job_store=FakeJobStore(), redis_client=FakeRedis(), config=Cfg(),
        run_async=lambda coro: coro, enqueue_worker=enqueue, await_worker=await_worker,
        owner_id="o", session_id="s", helper_profiles=profiles, verify_llm=verify_llm,
    )


@pytest.mark.asyncio
async def test_only_volunteers_are_enqueued():
    def llm(system, user):
        return "YES 0.9 relevant" if "maps code" in user else "NO 0.0 no"

    enqueued = []
    orch = _orch([("Planner", "maps code"), ("Web-Generator", "builds UIs")], llm, enqueued)
    job_id = await orch.start_async("find the parser", max_helpers=3)
    # Exactly one volunteer (Planner) enqueued; its payload carries no caller-chosen type.
    assert len(enqueued) == 1
    assert enqueued[0].subagent_type == "Planner"
    assert enqueued[0].bid_confidence == 0.9


@pytest.mark.asyncio
async def test_zero_volunteers_marks_done():
    def llm(system, user):
        return "NO 0.0 unrelated"

    enqueued = []
    orch = _orch([("Planner", "maps code")], llm, enqueued)
    job_id = await orch.start_async("x", max_helpers=3)
    assert enqueued == []
    rec = await orch._js.load(job_id)
    assert rec["status"] == "done"
