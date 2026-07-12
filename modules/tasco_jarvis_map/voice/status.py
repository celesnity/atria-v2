"""Shared voice-session status channel (Redis) for the local voice worker.

The console worker (voice env) runs the full local audio loop; the dashboard mic
button can't see into it, so the worker PUBLISHES each turn's state here and the
bridge (scripts/voice_session.py, map venv) READS it for the frontend to poll.
Both envs have `redis` + ATRIA_REDIS_URL, so this one module is the single source
of the status schema.

Key:   map:voice:{sid}      (JSON blob, TTL 3600s)
Value: {seq, state, transcript, reply, map_actions, session_id, error, ts}
  state: "idle" | "listening" | "thinking" | "speaking" | "error" | "stopped"
  seq:   monotonically increasing so the poller can tell turns apart

Single-writer (only the worker publishes) -> read-modify-write on `seq` is safe.
Best-effort: any Redis failure degrades to a no-op / empty read; the local voice
loop keeps working audibly, only the on-screen transcript/map update is skipped.
"""
from __future__ import annotations

import json
import os
import time

_TTL = 3600
_client = None
_client_failed = False


def _redis():
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client
    try:
        import redis
        url = os.environ.get("ATRIA_REDIS_URL", "redis://localhost:6379/0")
        _client = redis.Redis.from_url(
            url, decode_responses=True,
            socket_timeout=0.25, socket_connect_timeout=0.25)
        _client.ping()
    except Exception:  # noqa: BLE001 - best-effort; degrade to no-op
        _client = None
        _client_failed = True
    return _client


def _key(sid: str) -> str:
    return f"map:voice:{sid}"


def read(sid: str) -> dict:
    """Latest status blob for a session, or {} if none / Redis down."""
    r = _redis()
    if r is None:
        return {}
    try:
        raw = r.get(_key(sid))
        return json.loads(raw) if raw else {}
    except Exception:  # noqa: BLE001
        return {}


def publish(sid: str, *, state: str, bump: bool = True, **fields) -> dict:
    """Merge `state` + `fields` into the session blob and store it. Increments
    `seq` when bump=True (a new user turn / reply). Returns the stored blob (also
    returned when Redis is down so callers can still log locally)."""
    cur = read(sid)
    seq = int(cur.get("seq", 0)) + (1 if bump else 0)
    blob = {**cur, **fields, "state": state, "seq": seq,
            "session_id": sid, "ts": int(time.time())}
    # fields explicitly set to None clear the prior value (e.g. error reset)
    blob = {k: v for k, v in blob.items() if v is not None}
    r = _redis()
    if r is not None:
        try:
            r.set(_key(sid), json.dumps(blob, ensure_ascii=True), ex=_TTL)
        except Exception:  # noqa: BLE001
            pass
    return blob


def clear(sid: str) -> None:
    r = _redis()
    if r is None:
        return
    try:
        r.delete(_key(sid))
    except Exception:  # noqa: BLE001
        pass
