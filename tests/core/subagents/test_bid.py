import pytest

from atria.core.subagents.bid import parse_bid, run_bids


def test_parse_bid_yes_no():
    assert parse_bid("YES 0.9 owns the auth module")[0] is True
    assert parse_bid("no - unrelated")[0] is False
    assert parse_bid("garbage")[0] is False  # unparseable = decline (fail-closed)


@pytest.mark.asyncio
async def test_run_bids_independent_and_capped():
    profiles = [("Planner", "maps code"), ("Web-Generator", "builds UIs"),
                ("module_worker", "edits a module")]
    seen = []

    def fake_llm(system, user):
        seen.append(user)
        # Only Planner + module_worker say yes; Web-Generator declines.
        if "maps code" in user:
            return "YES 0.9 relevant"
        if "edits a module" in user:
            return "YES 0.6 maybe"
        return "NO 0.0 unrelated"

    bids = await run_bids("j1", "find and fix the parser", profiles, fake_llm,
                          max_helpers=1, now=1.0)
    # Each profile evaluated exactly once, independently.
    assert len(seen) == 3
    assert all(len([b for b in bids if b.responder == p[0]]) == 1 for p in profiles)
    # Capped to 1 volunteer — the highest-confidence yes (Planner).
    volunteers = [b.responder for b in bids if b.volunteered]
    assert volunteers == ["Planner"]


@pytest.mark.asyncio
async def test_run_bids_fail_closed_when_no_llm():
    bids = await run_bids("j1", "x", [("Planner", "maps code")], None,
                          max_helpers=3, now=1.0)
    assert bids[0].volunteered is False


@pytest.mark.asyncio
async def test_run_bids_fail_closed_on_error():
    def boom(system, user):
        raise RuntimeError("llm down")

    bids = await run_bids("j1", "x", [("Planner", "maps code")], boom,
                          max_helpers=3, now=1.0)
    assert bids[0].volunteered is False
