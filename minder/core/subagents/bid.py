"""Autonomous per-helper bidding for the broadcast blackboard (paper §3.2).

Each helper independently self-assesses one request against ITS OWN capability
profile — never a joint view of all profiles, so no coordinator "knows" every
capability. Bids run concurrently and fail closed: a missing verifier, an error,
or an unparseable reply all mean "do not volunteer".
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Callable

from minder.core.blackboard.models import Bid

logger = logging.getLogger(__name__)

_BID_SYSTEM = (
    "You are one helper agent deciding whether to volunteer for a request posted "
    "on a shared blackboard. You are given ONLY your own capability profile and the "
    "request. Reply with exactly one line: 'YES <confidence 0-1> <one-line reason>' "
    "if the request is within your capabilities, or 'NO <confidence 0-1> <reason>' "
    "if it is not. Volunteer only when you can genuinely contribute."
)

_YES = re.compile(r"^\s*yes\b", re.IGNORECASE)
_CONF = re.compile(r"([01](?:\.\d+)?)")


def parse_bid(reply: str) -> tuple[bool, float, str]:
    """Parse an LLM bid line into (volunteered, confidence, reason). Fail-closed."""
    text = (reply or "").strip()
    if not _YES.match(text):
        # Anything not starting with YES (incl. empty/garbage) is a decline.
        conf = 0.0
        m = _CONF.search(text)
        if m:
            try:
                conf = float(m.group(1))
            except ValueError:
                conf = 0.0
        return False, conf, text[:200]
    rest = text[3:].strip()
    m = _CONF.match(rest)
    conf = 0.0
    if m:
        try:
            conf = float(m.group(1))
        except ValueError:
            conf = 0.0
        rest = rest[m.end():].strip(" -\t")
    return True, conf, rest[:200]


def _bid_one(
    request_id: str, prompt: str, name: str, profile: str,
    verify_llm: Callable[[str, str], str] | None, now: float,
) -> Bid:
    """Evaluate a single helper's bid synchronously. Never raises."""
    if verify_llm is None:
        return Bid(request_id, name, False, "no verifier available", 0.0, now)
    user = f"Your capability profile:\n{profile}\n\nRequest:\n{prompt}"
    try:
        reply = verify_llm(_BID_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001 — fail closed
        logger.info("bid failed for %s: %s", name, exc)
        return Bid(request_id, name, False, "bid error", 0.0, now)
    volunteered, conf, reason = parse_bid(reply)
    return Bid(request_id, name, volunteered, reason, conf, now)


async def run_bids(
    request_id: str, prompt: str, profiles: list[tuple[str, str]],
    verify_llm: Callable[[str, str], str] | None, *, max_helpers: int, now: float,
) -> list[Bid]:
    """Run one independent bid per profile, concurrently, and cap volunteers.

    Returns a Bid per profile (order preserved). At most ``max_helpers`` bids keep
    ``volunteered=True`` — the highest-confidence yes-voters win; the rest are
    downgraded to declines with reason "capped".
    """
    raw = await asyncio.gather(*[
        asyncio.to_thread(_bid_one, request_id, prompt, name, profile, verify_llm, now)
        for name, profile in profiles
    ])
    yes = sorted([b for b in raw if b.volunteered],
                 key=lambda b: b.confidence, reverse=True)
    keep = {id(b) for b in yes[:max(0, max_helpers)]}
    out: list[Bid] = []
    for b in raw:
        if b.volunteered and id(b) not in keep:
            out.append(Bid(b.request_id, b.responder, False, "capped", b.confidence, b.ts))
        else:
            out.append(b)
    return out
