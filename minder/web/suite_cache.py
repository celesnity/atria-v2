"""Cross-request cache for the web path's RuntimeSuite.

Building a suite (skill discovery + agent/prompt/schema construction) costs
~0.5-1.5s and runs on every request. This caches it keyed by the inputs that
actually affect the build. The registry holds mutable per-run state, so:

- On a cache hit the caller resets per-run state before use.
- Concurrent same-key requests use *copy-on-contention*: if the cached suite is
  already in use, the second request builds a fresh (ephemeral) suite instead of
  sharing it — no serialization, no cross-session state bleed.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Hashable


@dataclass
class _Entry:
    suite: Any
    in_use: bool


def _noop() -> None:
    return None


class SuiteCache:
    """Bounded, thread-safe LRU of RuntimeSuites with copy-on-contention."""

    def __init__(self, maxsize: int = 8) -> None:
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._entries: "OrderedDict[Hashable, _Entry]" = OrderedDict()

    def acquire(self, key: Hashable, build_fn: Callable[[], Any]) -> tuple[Any, Callable[[], None]]:
        """Return (suite, release). Reuse a free cached suite for `key`, else
        build a fresh one. `release` must be called exactly once when done."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and not entry.in_use:
                entry.in_use = True
                self._entries.move_to_end(key)
                return entry.suite, lambda: self._release(key)

        # Miss or contended: build outside the lock (build may be slow).
        suite = build_fn()

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._entries[key] = _Entry(suite=suite, in_use=True)
                self._evict_locked()
                return suite, lambda: self._release(key)
            # A cached entry exists but was in use -> this suite is ephemeral.
            return suite, _noop

    def _release(self, key: Hashable) -> None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                entry.in_use = False

    def _evict_locked(self) -> None:
        # Drop the least-recently-used entry that is not currently in use.
        while len(self._entries) > self._maxsize:
            for k, e in list(self._entries.items()):
                if not e.in_use:
                    del self._entries[k]
                    break
            else:
                break  # everything in use; allow temporary overflow


def make_suite_cache_key(working_dir: Any, config: Any, mcp_manager: Any) -> tuple:
    """Signature of everything that affects a built suite.

    Includes today's date so the env block (which carries the date in the
    dynamic tail) is rebuilt at least daily; within a day, git-status staleness
    in the cached prompt is accepted (the prompt already labels it a snapshot).
    """
    import datetime

    cfg_sig = (
        getattr(config, "model", ""),
        getattr(config, "provider", ""),
        getattr(config, "fallback_model", ""),
        getattr(config, "agent_mode", "normal"),
        getattr(config, "temperature", None),
        getattr(config, "max_tokens", None),
        getattr(config, "max_context_tokens", None),
        getattr(config, "reasoning_effort", ""),
        getattr(config, "native_reasoning", True),
    )

    servers: tuple = ()
    if mcp_manager is not None:
        try:
            names = tuple(sorted(mcp_manager.list_servers()))
            connected = tuple(sorted(n for n in names if mcp_manager.is_connected(n)))
            servers = (names, connected)
        except Exception:
            servers = ()

    return (
        str(working_dir),
        cfg_sig,
        _skill_dirs_mtime_sig(working_dir),
        servers,
        datetime.date.today().isoformat(),
    )


def _skill_dirs_mtime_sig(working_dir: Any) -> tuple:
    """Max mtime of skill/module sources so a touched skill invalidates the key."""
    from pathlib import Path

    from minder.core.paths import get_paths

    candidates = [Path(str(working_dir)) / ".minder" / "skills"]
    try:
        candidates.append(get_paths().global_skills_dir)
    except Exception:
        pass
    try:
        from minder.core.modules.registry import resolve_modules_root

        root = resolve_modules_root()
        if root.is_dir():
            candidates.append(root)
    except Exception:
        pass

    sig = []
    for d in candidates:
        try:
            if not Path(d).is_dir():
                sig.append((str(d), 0.0))
                continue
            latest = 0.0
            for p in Path(d).rglob("*"):
                if p.suffix in (".py", ".md"):
                    latest = max(latest, p.stat().st_mtime)
            sig.append((str(d), latest))
        except Exception:
            sig.append((str(d), -1.0))
    return tuple(sig)
