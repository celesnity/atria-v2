"""Bridge for running async DB calls from synchronous code paths (REPL, CLI)."""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, Optional, TypeVar

T = TypeVar("T")

# Uvicorn's event loop, set at server startup so executor threads can reuse it.
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Register the server's event loop so run_sync can schedule onto it."""
    global _main_loop
    _main_loop = loop


def run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run *coro* synchronously.

    Priority:
    1. Already on a running loop → run_coroutine_threadsafe on that loop.
    2. No running loop but _main_loop is set and running (executor threads in
       web server) → run_coroutine_threadsafe on _main_loop, which owns the
       SQLAlchemy AsyncEngine.
    3. Fallback → asyncio.run() (CLI / REPL paths with no server loop).
    """
    try:
        loop = asyncio.get_running_loop()
        # We're inside an async context — hand off to that loop.
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)
    except RuntimeError:
        pass

    # No running loop in this thread (ThreadPoolExecutor worker).
    if _main_loop is not None and _main_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
        return future.result(timeout=60)

    # Pure CLI/REPL path — safe to create a temporary loop.
    return asyncio.run(coro)
