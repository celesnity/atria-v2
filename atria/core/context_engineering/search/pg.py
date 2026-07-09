"""Small synchronous Postgres helpers for search providers.

Opens one asyncpg connection per call via asyncio.run(). At hackathon corpus
scale (tens to hundreds of rows per query) this is simpler and safer than
sharing the app's async engine across event loops. Upgrade path: a pooled
executor if latency ever matters.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Sequence

import asyncpg


def _dsn() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _fetch(sql: str, args: Sequence[Any]) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(_dsn())
    try:
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def _execute(sql: str, args: Sequence[Any]) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


def fetch_all(sql: str, args: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """Run a SELECT and return rows as dicts ($1..$n params)."""
    return asyncio.run(_fetch(sql, args))


def execute(sql: str, args: Sequence[Any] = ()) -> None:
    """Run a DDL/DML statement ($1..$n params)."""
    asyncio.run(_execute(sql, args))
