import pytest

from minder.core.blackboard.models import Bid, Response
from minder.core.blackboard.response_store import BidStore, ResponseStore


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
async def test_response_store_roundtrip():
    r = FakeRedis()
    s = ResponseStore(r, run_id="sa_1", ttl=60)
    await s.add([Response(request_id="sa_1", responder="Planner", content="x",
                          confidence=0.7, ts=1.0)])
    got = await s.all()
    assert [x.responder for x in got] == ["Planner"]
    assert got[0].confidence == 0.7


@pytest.mark.asyncio
async def test_bid_store_roundtrip():
    r = FakeRedis()
    s = BidStore(r, run_id="sa_1", ttl=60)
    await s.add([Bid(request_id="sa_1", responder="Web-Generator", volunteered=False,
                     reason="n/a", confidence=0.0, ts=1.0)])
    got = await s.all()
    assert got[0].volunteered is False
