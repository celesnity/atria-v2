#!/usr/bin/env python
"""Per-conversation soft-cache for the map agent (multi-turn dialogue state).

A best-effort Redis store keyed by ``chat_session_id``. It lets the deterministic
fast path (a fresh subprocess per turn, with no shared memory) carry a little
context across turns -- the last resolved city / category / intent -- so a
follow-up like "toi o SG" after "benh vien" can re-scope instead of starting over.

Design constraints:
  * Soft / best-effort: ANY Redis problem (absent, slow, wrong version) degrades
    to a no-op with a short timeout, so the fast path never hangs or breaks.
  * TTL'd: an abandoned conversation self-clears after ``_TTL_SECONDS``.
  * Versioned: entries carry ``v``; a mismatch on load is treated as empty, so a
    schema change can never corrupt a live conversation.

Only the interactive dashboard path uses this; the benchmark never calls it.
"""
from __future__ import annotations

import json
import os
import sys

_TTL_SECONDS = 1800          # 30 min; refreshed on every write
_SCHEMA_VERSION = 2          # v2 adds results[] (ordered poi_ids) + time carry-over
_KEY_PREFIX = "map:ctx:"
_CONNECT_TIMEOUT = 0.25      # seconds; keep the fast path fast when Redis is down
_OP_TIMEOUT = 0.25

_client = None               # cached client (also a test seam: set directly)
_client_failed = False       # once a connection fails, stop retrying this process
_warned = False              # emit the "cache unreachable" warning at most once/process


def _redis_url() -> str:
    return os.environ.get("ATRIA_REDIS_URL", "redis://localhost:6379/0")


def _note_failure(exc: Exception) -> None:
    """Latch the failure (so the rest of this turn short-circuits instead of
    eating another timeout) and warn ONCE — a live Redis outage otherwise
    silently disables all multi-turn context with no operator signal."""
    global _client, _client_failed, _warned
    _client, _client_failed = None, True
    if not _warned:
        _warned = True
        print(f"WARN: map session cache unreachable at {_redis_url()} "
              f"({type(exc).__name__}: {exc}) -- multi-turn context disabled",
              file=sys.stderr)


def _redis():
    """Lazily build a short-timeout Redis client, or return None if unavailable."""
    global _client, _client_failed
    if _client is not None or _client_failed:
        return _client
    try:
        import redis  # redis>=5.0, already an Atria dependency
        _client = redis.Redis.from_url(
            _redis_url(),
            socket_connect_timeout=_CONNECT_TIMEOUT,
            socket_timeout=_OP_TIMEOUT,
            decode_responses=True,
        )
    except Exception as exc:  # noqa: BLE001 - any import/parse failure -> no cache
        _note_failure(exc)
    return _client


def _key(sid: str) -> str:
    return _KEY_PREFIX + sid


def load_context(sid) -> dict:
    """Return the cached dialogue state for ``sid``, or ``{}`` on any miss/failure."""
    if not sid:
        return {}
    cli = _redis()
    if cli is None:
        return {}
    try:
        raw = cli.get(_key(sid))
    except Exception as exc:  # noqa: BLE001 - Redis down/slow -> behave stateless
        _note_failure(exc)
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict) or data.get("v") != _SCHEMA_VERSION:
        return {}            # version/shape mismatch -> safe empty
    return data


def save_context(sid, ctx: dict) -> None:
    """Persist dialogue state for ``sid`` with a refreshed TTL. Best-effort."""
    if not sid or not isinstance(ctx, dict):
        return
    cli = _redis()
    if cli is None:
        return
    payload = dict(ctx)
    payload["v"] = _SCHEMA_VERSION
    try:
        cli.set(_key(sid), json.dumps(payload, ensure_ascii=False), ex=_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - never let a cache write break a turn
        _note_failure(exc)
        return


def clear_context(sid) -> None:
    """Delete the cached state for ``sid`` (chat reset / new conversation)."""
    if not sid:
        return
    cli = _redis()
    if cli is None:
        return
    try:
        cli.delete(_key(sid))
    except Exception as exc:  # noqa: BLE001
        _note_failure(exc)
        return


def _selftest() -> int:
    """`python session_context.py` — one-command 'is the session cache reachable?'."""
    url = _redis_url()
    try:
        import redis
        pong = redis.Redis.from_url(url, socket_connect_timeout=1,
                                    socket_timeout=1).ping()
        print(f"OK   map session cache reachable at {url} (ping={pong})")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL map session cache UNREACHABLE at {url}: "
              f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(_selftest())
