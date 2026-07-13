import pytest

from minder.core.blackboard.response_store import ResponseStore
from minder.core.tasks.tasks import _write_response


class FakeRedis:
    def __init__(self):
        self.h = {}
    async def hset(self, key, mapping=None):
        self.h.setdefault(key, {}).update(mapping or {})
    async def expire(self, key, ttl):
        return True
    async def hgetall(self, key):
        return {k.encode(): v.encode() for k, v in self.h.get(key, {}).items()}


@pytest.mark.asyncio
async def test_write_response_persists_answer():
    r = FakeRedis()
    await _write_response(r, "sa_1", "Planner", "found it at x.py:1", 0.8)
    got = await ResponseStore(r, run_id="sa_1", ttl=60).all()
    assert got[0].content == "found it at x.py:1"
    assert got[0].confidence == 0.8
