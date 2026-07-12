"""Redis hot-path store for a run's delegated task records (the task channel).

Sits beside the note channel (``BlackboardStore``). Tasks live in one hash keyed
``minder:bb:{run_id}:tasks``; a per-task claim flag guards against duplicate worker
delivery. The caller owns the redis client lifecycle.
"""

from __future__ import annotations

import json

from minder.core.blackboard.models import Task

_PREFIX = "minder:bb:"


class TaskStore:
    """Hash of ``task_id -> Task`` for one run, plus atomic claim flags."""

    def __init__(self, redis: object, run_id: str, ttl: int) -> None:
        self._redis = redis
        self._hkey = f"{_PREFIX}{run_id}:tasks"
        self._claim = f"{_PREFIX}{run_id}:claim:"
        self._ttl = ttl

    async def add(self, tasks: list[Task]) -> None:
        """Write each task as a hash field and refresh the TTL."""
        if not tasks:
            return
        mapping = {t.id: json.dumps(t.to_dict()) for t in tasks}
        await self._redis.hset(self._hkey, mapping=mapping)  # type: ignore[attr-defined]
        await self._redis.expire(self._hkey, self._ttl)  # type: ignore[attr-defined]

    async def get(self, task_id: str) -> Task | None:
        raw = await self._redis.hget(self._hkey, task_id)  # type: ignore[attr-defined]
        if raw is None:
            return None
        s = raw.decode() if isinstance(raw, bytes) else raw
        return Task.from_dict(json.loads(s))

    async def claim(self, task_id: str) -> bool:
        """Atomically claim a task. Returns True only for the first caller.

        Uses ``SET NX`` on a per-task flag so redelivery by an at-least-once broker
        cannot run the same task twice. On success flips the task's status to
        ``claimed``.
        """
        ok = await self._redis.set(  # type: ignore[attr-defined]
            self._claim + task_id, "1", nx=True, ex=self._ttl
        )
        if not ok:
            return False
        await self.set_status(task_id, "claimed")
        return True

    async def set_status(self, task_id: str, status: str, result: str = "") -> None:
        task = await self.get(task_id)
        if task is None:
            return
        updated = Task(
            id=task.id,
            subagent_type=task.subagent_type,
            prompt=task.prompt,
            status=status,
            result=result or task.result,
            ts=task.ts,
        )
        await self._redis.hset(  # type: ignore[attr-defined]
            self._hkey, task_id, json.dumps(updated.to_dict())
        )
        await self._redis.expire(self._hkey, self._ttl)  # type: ignore[attr-defined]

    async def all(self) -> list[Task]:
        raw = await self._redis.hgetall(self._hkey)  # type: ignore[attr-defined]
        out: list[Task] = []
        for v in (raw or {}).values():
            s = v.decode() if isinstance(v, bytes) else v
            out.append(Task.from_dict(json.loads(s)))
        return out
