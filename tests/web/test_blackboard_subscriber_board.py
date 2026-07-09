import json

import pytest

from atria.web.blackboard_subscriber import BlackboardSubscriber


class FakeBroadcaster:
    def __init__(self):
        self.sent = []

    async def broadcast(self, msg):
        self.sent.append(msg)


@pytest.mark.asyncio
async def test_board_bid_event_forwarded():
    b = FakeBroadcaster()
    sub = BlackboardSubscriber(redis=None, broadcaster=b)
    await sub._forward({
        "channel": b"atria:bb:sa_1:board",
        "data": json.dumps({"kind": "bid", "request_id": "sa_1", "responder": "Planner"}),
    })
    assert b.sent[0]["type"] == "blackboard.bid"
    assert b.sent[0]["data"]["responder"] == "Planner"
