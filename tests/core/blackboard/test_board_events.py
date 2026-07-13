import json

import pytest

from minder.core.blackboard.board_events import publish_board_event


class FakeRedis:
    def __init__(self):
        self.published = []

    async def publish(self, channel, payload):
        self.published.append((channel, payload))


@pytest.mark.asyncio
async def test_publish_board_event():
    r = FakeRedis()
    await publish_board_event(r, "sa_1", "bid", {"responder": "Planner", "volunteered": True})
    channel, payload = r.published[0]
    assert channel == "minder:bb:sa_1:board"
    d = json.loads(payload)
    assert d["kind"] == "bid" and d["responder"] == "Planner"
