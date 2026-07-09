"""Response board (β_r) and bid roster stores — Redis hashes, one per run.

``ResponseStore`` holds helper answers exclusive to the main agent (paper
footnote 2). ``BidStore`` holds every helper's self-assessment (volunteer or
decline + reason) for telemetry and the web-ui viewer. Both sit beside the note
channel (``BlackboardStore``); the caller owns the redis client lifecycle.
"""
from __future__ import annotations

import json

from atria.core.blackboard.models import Bid, Response

_PREFIX = "atria:bb:"


class ResponseStore:
    """Hash of ``responder -> Response`` for one request/run."""

    def __init__(self, redis: object, run_id: str, ttl: int) -> None:
        self._redis = redis
        self._hkey = f"{_PREFIX}{run_id}:responses"
        self._ttl = ttl

    async def add(self, responses: list[Response]) -> None:
        if not responses:
            return
        mapping = {r.responder: json.dumps(r.to_dict()) for r in responses}
        await self._redis.hset(self._hkey, mapping=mapping)  # type: ignore[attr-defined]
        await self._redis.expire(self._hkey, self._ttl)  # type: ignore[attr-defined]

    async def all(self) -> list[Response]:
        raw = await self._redis.hgetall(self._hkey)  # type: ignore[attr-defined]
        out: list[Response] = []
        for v in (raw or {}).values():
            s = v.decode() if isinstance(v, bytes) else v
            out.append(Response.from_dict(json.loads(s)))
        return out


class BidStore:
    """Hash of ``responder -> Bid`` for one request/run."""

    def __init__(self, redis: object, run_id: str, ttl: int) -> None:
        self._redis = redis
        self._hkey = f"{_PREFIX}{run_id}:bids"
        self._ttl = ttl

    async def add(self, bids: list[Bid]) -> None:
        if not bids:
            return
        mapping = {b.responder: json.dumps(b.to_dict()) for b in bids}
        await self._redis.hset(self._hkey, mapping=mapping)  # type: ignore[attr-defined]
        await self._redis.expire(self._hkey, self._ttl)  # type: ignore[attr-defined]

    async def all(self) -> list[Bid]:
        raw = await self._redis.hgetall(self._hkey)  # type: ignore[attr-defined]
        out: list[Bid] = []
        for v in (raw or {}).values():
            s = v.decode() if isinstance(v, bytes) else v
            out.append(Bid.from_dict(json.loads(s)))
        return out
