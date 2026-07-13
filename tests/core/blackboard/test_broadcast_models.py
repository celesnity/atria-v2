from minder.core.blackboard.models import Bid, Request, Response


def test_request_roundtrip():
    r = Request(id="j1", prompt="find the auth module", status="open", ts=1.0)
    assert Request.from_dict(r.to_dict()) == r


def test_response_roundtrip():
    r = Response(request_id="j1", responder="Planner", content="see auth.py:12",
                 confidence=0.8, ts=2.0)
    assert Response.from_dict(r.to_dict()) == r


def test_bid_roundtrip_and_decline():
    b = Bid(request_id="j1", responder="Web-Generator", volunteered=False,
            reason="no UI work needed", confidence=0.1, ts=3.0)
    d = b.to_dict()
    assert d["volunteered"] is False
    assert Bid.from_dict(d) == b
