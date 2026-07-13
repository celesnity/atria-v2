# Unified Subagent on the Blackboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the `subagent` / `divide` / `parallel` delegation concepts into one **subagent** primitive whose tasks live on the blackboard and whose results are written back as shared-context notes.

**Architecture:** The main agent calls one tool, `subagent(tasks=[...])`, which writes flat `Task` records to a new blackboard **task channel** and enqueues one TaskIQ worker per task. Each worker reads its task *from the blackboard* (source of task), runs the named subagent type (which writes result notes to the shared-context channel), and marks the task done/failed on the blackboard. `get_subagent_output(job_id)` aggregates task statuses and renders the notes digest. Divide's decomposer/scheduler and all of parallel (candidate racing + judge) are deleted.

**Tech Stack:** Python 3.11+, asyncio, Redis (`redis.asyncio`), TaskIQ, pydantic, pytest + `pytest.mark.asyncio` + `fakeredis.aioredis`.

## Global Constraints

- Line length 100 (Black + Ruff); type hints on public APIs (mypy strict); Google-style docstrings.
- Never use table format in prompt/tool-description markdown — prose or bullets only.
- Redis + a running `minder-worker` are required for any delegation (always-worker; no in-process path).
- Blackboard keys are namespaced `minder:bb:{run_id}...`; job records use `JobStore` prefixes.
- Tests use `from fakeredis import aioredis as fake_aioredis` and `fake_aioredis.FakeRedis()`.
- Do not commit `Co-Authored-By: Claude` trailers. Run the full test suite once at the end, not per task.

## File Structure

- Create `minder/core/blackboard/models.py` additions — `Task` dataclass + status constants (results/task record).
- Create `minder/core/blackboard/task_store.py` — `TaskStore`: add / get / claim / set_status / all over a Redis hash.
- Create `minder/core/subagents/__init__.py` — package marker.
- Create `minder/core/subagents/orchestrator.py` — `SubagentOrchestrator`: write tasks + enqueue workers + collect.
- Create `minder/core/subagents/tools.py` — `build_subagent_orchestrator` + `execute_subagent_fanout` + `execute_get_subagent_output`.
- Modify `minder/core/orchestration/job_store.py` — add `SUBAGENT_PREFIX`.
- Modify `minder/core/tasks/payload.py` — add `subagent_task_id`.
- Modify `minder/core/tasks/tasks.py` — worker claims + reads task from blackboard, marks status.
- Modify `minder/core/context_engineering/tools/registry_mixins/orchestration_ops.py` — replace solve/divide/parallel handlers with subagent handlers.
- Delete `minder/core/context_engineering/tools/registry_mixins/subagent_ops.py` — move `_get_repo_dir` into orchestration_ops.
- Modify `minder/core/context_engineering/tools/registry_mixins/__init__.py` and `registry.py` — drop `SubagentOpsMixin`, re-route tool names.
- Modify `minder/core/agents/subagents/task_tool.py` — `spawn_subagent` → `subagent`, `tasks[]` signature.
- Modify `minder/core/agents/components/schemas/builtin/orchestration_tools.py` — replace `solve`/`get_solve_result` schemas with `subagent`/`get_subagent_output`.
- Delete `minder/core/parallel/` (whole dir), `minder/core/divide/decompose.py`, `minder/core/divide/scheduler.py`.
- Delete prompt sections `templates/tools/tool-solve.md`, `tool-get-solve-result.md`; add `tool-subagent.md`, `tool-get-subagent-output.md`; edit `main-subagent-guide.md`.

---

### Task 1: `Task` model + status constants

**Files:**
- Modify: `minder/core/blackboard/models.py`
- Test: `tests/core/blackboard/test_models.py`

**Interfaces:**
- Produces: `TASK_STATUSES: tuple[str, ...]`; `Task` dataclass with fields `id: str, subagent_type: str, prompt: str, status: str = "pending", result: str = "", ts: float = 0.0`, and `to_dict() -> dict` / `from_dict(d: dict) -> Task`.

- [ ] **Step 1: Write the failing test**

Append to `tests/core/blackboard/test_models.py`:

```python
def test_task_roundtrips_through_dict():
    from minder.core.blackboard.models import Task, TASK_STATUSES

    assert "pending" in TASK_STATUSES and "done" in TASK_STATUSES
    t = Task(id="t0", subagent_type="code_explorer", prompt="find X", ts=1.5)
    assert t.status == "pending" and t.result == ""
    again = Task.from_dict(t.to_dict())
    assert again == t
    done = Task.from_dict({"id": "t1", "subagent_type": "solver", "prompt": "p",
                           "status": "done", "result": "ok", "ts": 2.0})
    assert done.status == "done" and done.result == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/blackboard/test_models.py::test_task_roundtrips_through_dict -v`
Expected: FAIL with `ImportError: cannot import name 'Task'`.

- [ ] **Step 3: Write minimal implementation**

Add to `minder/core/blackboard/models.py` (below the existing `Note` class):

```python
TASK_STATUSES: tuple[str, ...] = ("pending", "claimed", "done", "failed")


@dataclass(frozen=True)
class Task:
    """One unit of delegated work on the blackboard task channel."""

    id: str
    subagent_type: str
    prompt: str
    status: str = "pending"
    result: str = ""
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "subagent_type": self.subagent_type,
                "prompt": self.prompt, "status": self.status,
                "result": self.result, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(id=d["id"], subagent_type=d["subagent_type"], prompt=d["prompt"],
                   status=d.get("status", "pending"), result=d.get("result", ""),
                   ts=float(d.get("ts", 0.0)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/blackboard/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add minder/core/blackboard/models.py tests/core/blackboard/test_models.py
git commit -m "feat(blackboard): add Task model + status constants"
```

---

### Task 2: `TaskStore` — task channel over Redis

**Files:**
- Create: `minder/core/blackboard/task_store.py`
- Test: `tests/core/blackboard/test_task_store.py`

**Interfaces:**
- Consumes: `Task` from Task 1.
- Produces: `TaskStore(redis, run_id: str, ttl: int)` with async methods `add(tasks: list[Task]) -> None`, `get(task_id: str) -> Task | None`, `claim(task_id: str) -> bool` (atomic; True only for the first caller), `set_status(task_id: str, status: str, result: str = "") -> None`, `all() -> list[Task]`. Hash key is `minder:bb:{run_id}:tasks`; claim flag key is `minder:bb:{run_id}:claim:{task_id}`.

- [ ] **Step 1: Write the failing test**

Create `tests/core/blackboard/test_task_store.py`:

```python
import pytest

from minder.core.blackboard.models import Task
from minder.core.blackboard.task_store import TaskStore


@pytest.mark.asyncio
async def test_add_get_all_roundtrip():
    from fakeredis import aioredis as fake_aioredis

    store = TaskStore(fake_aioredis.FakeRedis(), run_id="r1", ttl=60)
    await store.add([Task("t0", "solver", "a", ts=1.0), Task("t1", "code_explorer", "b", ts=2.0)])
    got = await store.get("t0")
    assert got is not None and got.subagent_type == "solver"
    ids = sorted(t.id for t in await store.all())
    assert ids == ["t0", "t1"]


@pytest.mark.asyncio
async def test_claim_is_exclusive_and_sets_status():
    from fakeredis import aioredis as fake_aioredis

    store = TaskStore(fake_aioredis.FakeRedis(), run_id="r2", ttl=60)
    await store.add([Task("t0", "solver", "a")])
    assert await store.claim("t0") is True
    assert await store.claim("t0") is False
    assert (await store.get("t0")).status == "claimed"


@pytest.mark.asyncio
async def test_set_status_updates_result():
    from fakeredis import aioredis as fake_aioredis

    store = TaskStore(fake_aioredis.FakeRedis(), run_id="r3", ttl=60)
    await store.add([Task("t0", "solver", "a")])
    await store.set_status("t0", "done", result="finished")
    got = await store.get("t0")
    assert got.status == "done" and got.result == "finished"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/blackboard/test_task_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'minder.core.blackboard.task_store'`.

- [ ] **Step 3: Write minimal implementation**

Create `minder/core/blackboard/task_store.py`:

```python
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
        updated = Task(id=task.id, subagent_type=task.subagent_type, prompt=task.prompt,
                       status=status, result=result or task.result, ts=task.ts)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/blackboard/test_task_store.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add minder/core/blackboard/task_store.py tests/core/blackboard/test_task_store.py
git commit -m "feat(blackboard): add TaskStore task channel with atomic claim"
```

---

### Task 3: `SubagentOrchestrator` — write tasks, enqueue workers, collect

**Files:**
- Create: `minder/core/subagents/__init__.py`
- Create: `minder/core/subagents/orchestrator.py`
- Modify: `minder/core/orchestration/job_store.py` (add `SUBAGENT_PREFIX`)
- Test: `tests/core/subagents/test_orchestrator.py`

**Interfaces:**
- Consumes: `TaskStore` (Task 2); `JobStore`; `SubagentTaskPayload`; `render_digest`.
- Produces: `SubagentOrchestrator(job_store, redis_client, config, run_async, enqueue_worker, await_worker, owner_id, session_id, working_dir="", progress_cb=None)` with `start(tasks: list[dict]) -> str` and `collect(job_id: str, block: bool = True, timeout_ms: int = 30000) -> dict`. Each `tasks` item is `{"subagent_type": str, "prompt": str}`. `collect` returns `{"status", "tasks": [{"id","subagent_type","status"}], "digest": str}`.
  - `enqueue_worker(payload: SubagentTaskPayload) -> Awaitable[str]` returns a broker task id.
  - `await_worker(task_ids: list[str]) -> Awaitable[tuple[str, dict]]` resolves when any completes.

- [ ] **Step 1: Add the job-store prefix**

In `minder/core/orchestration/job_store.py`, below `DIVIDE_PREFIX`:

```python
SUBAGENT_PREFIX = "minder:sajob:"
```

- [ ] **Step 2: Write the failing test**

Create `tests/core/subagents/__init__.py` (empty) and `tests/core/subagents/test_orchestrator.py`:

```python
import asyncio

import pytest

from minder.core.blackboard.task_store import TaskStore
from minder.core.orchestration.job_store import JobStore, SUBAGENT_PREFIX
from minder.core.subagents.orchestrator import SubagentOrchestrator


class _Cfg:
    pjob_ttl = 60


def _make_orch(redis, enqueued, done_event):
    async def enqueue_worker(payload):
        enqueued.append(payload)
        return f"tk_{payload.subagent_task_id}"

    async def await_worker(task_ids):
        # Resolve immediately; the worker (faked) marks the task done itself.
        await asyncio.sleep(0)
        done_event.set()
        return task_ids[0], {"status": "done"}

    return SubagentOrchestrator(
        job_store=JobStore(redis, SUBAGENT_PREFIX),
        redis_client=redis,
        config=_Cfg(),
        run_async=lambda coro: asyncio.get_event_loop().run_until_complete(coro),
        enqueue_worker=enqueue_worker,
        await_worker=await_worker,
        owner_id="o",
        session_id="s",
    )


@pytest.mark.asyncio
async def test_start_writes_tasks_and_enqueues_one_worker_each():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    enqueued: list = []
    orch = _make_orch(redis, enqueued, asyncio.Event())
    job_id = await orch.start_async(
        [{"subagent_type": "code_explorer", "prompt": "a"},
         {"subagent_type": "solver", "prompt": "b"}]
    )
    rec = await JobStore(redis, SUBAGENT_PREFIX).load(job_id)
    assert rec is not None and len(rec["task_ids"]) == 2
    assert len(enqueued) == 2
    assert {p.subagent_task_id for p in enqueued} == set(rec["task_ids"])
    store = TaskStore(redis, run_id=rec["bb_id"], ttl=60)
    assert {t.prompt for t in await store.all()} == {"a", "b"}


@pytest.mark.asyncio
async def test_collect_reports_task_statuses_and_digest():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    orch = _make_orch(redis, [], asyncio.Event())
    job_id = await orch.start_async([{"subagent_type": "solver", "prompt": "b"}])
    rec = await JobStore(redis, SUBAGENT_PREFIX).load(job_id)
    await TaskStore(redis, run_id=rec["bb_id"], ttl=60).set_status(
        rec["task_ids"][0], "done", result="ok"
    )
    out = await orch.collect_async(job_id)
    assert out["status"] in ("running", "done")
    assert out["tasks"][0]["status"] == "done"
    assert "digest" in out
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/core/subagents/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'minder.core.subagents'`.

- [ ] **Step 4: Write minimal implementation**

Create `minder/core/subagents/__init__.py` (empty file), then `minder/core/subagents/orchestrator.py`:

```python
"""Subagent fan-out coordinator: write tasks to the blackboard, enqueue one worker
per task, collect statuses + notes. Worker I/O is injected (decoupled from TaskIQ)."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable

from minder.core.blackboard.models import Task
from minder.core.blackboard.render import render_digest
from minder.core.blackboard.store import BlackboardStore
from minder.core.blackboard.task_store import TaskStore
from minder.core.orchestration.job_store import JobStore
from minder.core.tasks.payload import SubagentTaskPayload

logger = logging.getLogger(__name__)


class SubagentOrchestrator:
    """Run one subagent fan-out job over the injected worker broker."""

    def __init__(
        self,
        job_store: JobStore,
        redis_client: Any,
        config: Any,
        run_async: Callable[[Any], Any],
        enqueue_worker: Callable[[SubagentTaskPayload], Awaitable[str]],
        await_worker: Callable[[list[str]], Awaitable[tuple[str, dict]]],
        owner_id: str,
        session_id: str,
        working_dir: str = "",
        progress_cb: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._js = job_store
        self._redis = redis_client
        self._cfg = config
        self._run_async = run_async
        self._enqueue = enqueue_worker
        self._await = await_worker
        self._owner = owner_id
        self._session = session_id
        self._working_dir = working_dir
        self._cb = progress_cb

    def _emit(self, stage: str, data: dict) -> None:
        if self._cb is None:
            return
        try:
            self._cb(stage, data)
        except Exception as exc:  # noqa: BLE001 — telemetry never breaks the job
            logger.warning("subagent progress_cb failed at %s: %s", stage, exc)

    def start(self, tasks: list[dict]) -> str:
        return self._run_async(self.start_async(tasks))

    def collect(self, job_id: str, block: bool = True, timeout_ms: int = 30000) -> dict:
        return self._run_async(self.collect_async(job_id))

    async def start_async(self, tasks: list[dict]) -> str:
        """Persist tasks to the blackboard, enqueue one worker each, return job_id."""
        job_id = uuid.uuid4().hex[:12]
        bb_id = "sa_" + job_id
        now = time.time()
        task_objs = [
            Task(id=f"t{i}", subagent_type=str(t.get("subagent_type") or "general-purpose"),
                 prompt=str(t.get("prompt") or ""), ts=now)
            for i, t in enumerate(tasks)
        ]
        store = TaskStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl)
        await store.add(task_objs)

        record = {"job_id": job_id, "bb_id": bb_id,
                  "task_ids": [t.id for t in task_objs], "status": "running"}
        await self._js.save(job_id, record, ttl=self._cfg.pjob_ttl)
        self._emit("started", {"job_id": job_id,
                               "tasks": [{"id": t.id, "subagent_type": t.subagent_type}
                                         for t in task_objs]})

        enqueued: list[str] = []
        for i, t in enumerate(task_objs):
            payload = SubagentTaskPayload(
                session_id=self._session, owner_id=self._owner,
                subagent_type=t.subagent_type, prompt=t.prompt,
                working_dir=self._working_dir, config_snapshot={},
                blackboard_task_id=bb_id, thread_id=i, subagent_task_id=t.id,
            )
            enqueued.append(await self._enqueue(payload))

        asyncio.create_task(self._await_all(job_id, record, enqueued))
        return job_id

    async def _await_all(self, job_id: str, record: dict, task_ids: list[str]) -> None:
        """Drain worker completions, then flip the job to done. Never re-raises."""
        try:
            pending = set(task_ids)
            while pending:
                tid, _ = await self._await(list(pending))
                pending.discard(tid)
            record["status"] = "done"
            await self._js.save(job_id, record, ttl=self._cfg.pjob_ttl)
            self._emit("done", {"job_id": job_id, "status": "done"})
        except Exception as exc:  # noqa: BLE001 — background task must not crash silently
            logger.exception("subagent workers crashed for %s: %s", job_id, exc)

    async def collect_async(self, job_id: str) -> dict:
        rec = await self._js.load(job_id)
        if rec is None:
            return {"status": "unknown", "error": f"no such job {job_id}", "tasks": [], "digest": ""}
        bb_id = rec["bb_id"]
        tasks = await TaskStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl).all()
        notes = await BlackboardStore(self._redis, task_id=bb_id, ttl=self._cfg.pjob_ttl).read_all()
        return {
            "status": rec.get("status", "running"),
            "tasks": [{"id": t.id, "subagent_type": t.subagent_type, "status": t.status}
                      for t in sorted(tasks, key=lambda x: x.id)],
            "digest": render_digest(notes, viewer_id=0, window_tokens=2000),
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/core/subagents/test_orchestrator.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add minder/core/subagents/__init__.py minder/core/subagents/orchestrator.py \
        minder/core/orchestration/job_store.py tests/core/subagents/
git commit -m "feat(subagents): add SubagentOrchestrator fan-out coordinator"
```

---

### Task 4: Orchestrator builder + tool handlers

**Files:**
- Create: `minder/core/subagents/tools.py`
- Test: `tests/core/subagents/test_tools.py`

**Interfaces:**
- Consumes: `SubagentOrchestrator` (Task 3); `ensure_async_redis`, `make_run_async` from `minder.core.orchestration.bridge`; `JobStore`, `SUBAGENT_PREFIX`.
- Produces:
  - `build_subagent_orchestrator(task_client, config, owner_id, session_id, working_dir="", progress_cb=None, redis_client=None) -> SubagentOrchestrator`.
  - `execute_subagent_fanout(arguments: dict, orchestrator) -> dict` — reads `arguments["tasks"]` (list of `{subagent_type, prompt}`), returns `{"success", "job_id", "status", "output"}`.
  - `execute_get_subagent_output(arguments: dict, orchestrator) -> dict` — reads `arguments["job_id"]`, returns `{"success", "output"}` where output is the collect dict.

- [ ] **Step 1: Write the failing test**

Create `tests/core/subagents/test_tools.py`:

```python
from minder.core.subagents.tools import execute_get_subagent_output, execute_subagent_fanout


class _Orch:
    def __init__(self):
        self.started = None

    def start(self, tasks):
        self.started = tasks
        return "job123"

    def collect(self, job_id, block=True, timeout_ms=30000):
        return {"status": "done", "tasks": [], "digest": ""}


def test_fanout_requires_tasks():
    out = execute_subagent_fanout({}, _Orch())
    assert out["success"] is False and "tasks" in out["error"]


def test_fanout_starts_job():
    orch = _Orch()
    out = execute_subagent_fanout(
        {"tasks": [{"subagent_type": "solver", "prompt": "p"}]}, orch
    )
    assert out["success"] is True and out["job_id"] == "job123"
    assert orch.started[0]["prompt"] == "p"


def test_get_output_requires_job_id():
    out = execute_get_subagent_output({}, _Orch())
    assert out["success"] is False


def test_get_output_returns_collect():
    out = execute_get_subagent_output({"job_id": "job123"}, _Orch())
    assert out["success"] is True and out["output"]["status"] == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/subagents/test_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'minder.core.subagents.tools'`.

- [ ] **Step 3: Write minimal implementation**

Create `minder/core/subagents/tools.py`:

```python
"""Tool handlers + orchestrator builder for the unified ``subagent`` tool.

Mirrors the old divide/parallel tool builders but without decomposition, DAG
scheduling, or candidate judging. ``subagent`` writes flat tasks to the
blackboard and fans one worker out per task; ``get_subagent_output`` collects.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from minder.core.orchestration.bridge import ensure_async_redis, make_run_async
from minder.core.orchestration.job_store import SUBAGENT_PREFIX, JobStore
from minder.core.subagents.orchestrator import SubagentOrchestrator
from minder.core.tasks.payload import SubagentTaskPayload

logger = logging.getLogger(__name__)


def build_subagent_orchestrator(
    task_client: Any,
    config: Any,
    owner_id: str,
    session_id: str,
    working_dir: str = "",
    progress_cb: Any = None,
    redis_client: Any = None,
) -> SubagentOrchestrator:
    """Construct a SubagentOrchestrator that fans workers over the task broker."""
    sub_cfg = getattr(config, "divide", None) or config
    run_async = make_run_async(task_client)
    redis_client = ensure_async_redis(
        redis_client, getattr(sub_cfg, "redis_url", "redis://localhost:6379/0")
    )
    broker = task_client._broker

    async def enqueue_worker(payload: SubagentTaskPayload) -> str:
        from minder.core.tasks import meta
        from minder.core.tasks.client import _TASK_NAME

        task = broker.find_task(_TASK_NAME)
        if task is None:
            raise RuntimeError(f"task {_TASK_NAME} not registered")
        kicked = await task.kiq(payload.model_dump())
        await meta.record_enqueue(redis_client, kicked.task_id, payload.session_id)
        return kicked.task_id

    async def await_worker(task_ids: list[str]) -> tuple[str, dict]:
        backend = broker.result_backend
        while True:
            for tid in task_ids:
                if await backend.is_result_ready(tid):
                    res = await backend.get_result(tid, with_logs=False)
                    if res.is_err:
                        return tid, {"status": "failed", "error": str(res.error)}
                    return tid, {**(res.return_value or {}), "status": "done"}
            await asyncio.sleep(0.25)

    return SubagentOrchestrator(
        job_store=JobStore(redis_client, SUBAGENT_PREFIX),
        redis_client=redis_client,
        config=sub_cfg,
        run_async=run_async,
        enqueue_worker=enqueue_worker,
        await_worker=await_worker,
        owner_id=owner_id,
        session_id=session_id,
        working_dir=working_dir,
        progress_cb=progress_cb,
    )


def execute_subagent_fanout(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Write tasks to the blackboard and fan workers out. Returns a job handle."""
    tasks = arguments.get("tasks")
    if not tasks or not isinstance(tasks, list):
        return {"success": False, "error": "tasks (non-empty list) is required", "output": None}
    try:
        job_id = orchestrator.start(tasks)
    except Exception as exc:  # noqa: BLE001 — surface as tool error, never crash the loop
        logger.warning("subagent fan-out start failed: %s", exc)
        return {"success": False, "error": f"subagent failed: {exc}", "output": None}
    return {
        "success": True,
        "job_id": job_id,
        "status": "running",
        "output": (
            f"[SUBAGENT STARTED] job_id={job_id} with {len(tasks)} task(s). "
            "Use get_subagent_output(job_id) to poll and collect results."
        ),
    }


def execute_get_subagent_output(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Collect task statuses + the shared-context notes digest for a job."""
    job_id = arguments.get("job_id", "")
    if not job_id:
        return {"success": False, "error": "job_id is required", "output": None}
    try:
        result = orchestrator.collect(
            job_id, block=arguments.get("block", True),
            timeout_ms=arguments.get("timeout", 30000),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_subagent_output failed: %s", exc)
        return {"success": False, "error": f"get_subagent_output failed: {exc}", "output": None}
    return {"success": result.get("status") != "unknown", "output": result}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/subagents/test_tools.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add minder/core/subagents/tools.py tests/core/subagents/test_tools.py
git commit -m "feat(subagents): add builder + subagent/get_subagent_output tool handlers"
```

---

### Task 5: Worker reads task from the blackboard + marks status

**Files:**
- Modify: `minder/core/tasks/payload.py`
- Modify: `minder/core/tasks/tasks.py`
- Test: `tests/core/tasks/test_worker_blackboard_task.py`

**Interfaces:**
- Consumes: `TaskStore` (Task 2); `SubagentTaskPayload`.
- Produces: `SubagentTaskPayload.subagent_task_id: str | None`. Worker behaviour: when `subagent_task_id` is set, claim the task (skip if already claimed), read `subagent_type`+`prompt` from the blackboard `Task` (authoritative), run it, then `set_status("done"|"failed", result=<summary>)`.
  - New helper `minder.core.tasks.tasks._claim_and_load(redis, bb_id, task_id, ttl) -> Task | None` (returns the claimed Task, or None if unclaimable/missing).

- [ ] **Step 1: Add the payload field**

In `minder/core/tasks/payload.py`, add below `thread_id`:

```python
    subagent_task_id: str | None = None
```

- [ ] **Step 2: Write the failing test**

Create `tests/core/tasks/test_worker_blackboard_task.py`:

```python
import pytest

from minder.core.blackboard.models import Task
from minder.core.blackboard.task_store import TaskStore
from minder.core.tasks.tasks import _claim_and_load


@pytest.mark.asyncio
async def test_claim_and_load_returns_task_once():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    store = TaskStore(redis, run_id="sa_x", ttl=60)
    await store.add([Task("t0", "solver", "do the thing")])

    first = await _claim_and_load(redis, "sa_x", "t0", 60)
    assert first is not None and first.prompt == "do the thing"
    # Redelivery: already claimed → None (worker skips duplicate execution).
    assert await _claim_and_load(redis, "sa_x", "t0", 60) is None


@pytest.mark.asyncio
async def test_claim_and_load_missing_task_is_none():
    from fakeredis import aioredis as fake_aioredis

    redis = fake_aioredis.FakeRedis()
    assert await _claim_and_load(redis, "sa_x", "nope", 60) is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/core/tasks/test_worker_blackboard_task.py -v`
Expected: FAIL with `ImportError: cannot import name '_claim_and_load'`.

- [ ] **Step 4: Write minimal implementation**

In `minder/core/tasks/tasks.py`, add imports at the top (after the existing imports):

```python
import os

from minder.core.blackboard.task_store import TaskStore
```

Add this helper above `run_background_subagent`:

```python
async def _claim_and_load(redis: Any, bb_id: str, task_id: str, ttl: int):
    """Claim ``task_id`` on the blackboard and return its Task, or None.

    Returns None when the task is missing or already claimed (at-least-once
    redelivery) so the worker never runs the same delegated task twice.
    """
    store = TaskStore(redis, run_id=bb_id, ttl=ttl)
    if not await store.claim(task_id):
        return None
    return await store.get(task_id)
```

Then rewrite `run_background_subagent` so a blackboard-sourced task is claimed, read, run, and marked. Replace the function body with:

```python
@broker.task(task_name="minder.core.tasks.tasks.run_background_subagent")
async def run_background_subagent(payload: dict) -> dict:
    """Rebuild a headless runtime from the payload and run the subagent.

    When the payload names a ``subagent_task_id`` the task is read from the
    blackboard (the source of task), claimed to guard against redelivery, and its
    final status is written back to the blackboard task channel.
    """
    p = SubagentTaskPayload.model_validate(payload)
    deps: Any = None
    redis: Any = None
    task_store: Any = None
    if p.subagent_task_id and p.blackboard_task_id:
        import redis.asyncio as aioredis  # noqa: F811 — local import mirrors provision.py

        url = os.environ.get("MINDER_REDIS_URL", "redis://localhost:6379/0")
        redis = aioredis.from_url(url)
        claimed = await _claim_and_load(redis, p.blackboard_task_id, p.subagent_task_id, 3600)
        if claimed is None:
            await redis.aclose()
            return {"success": True, "content": "skipped (already claimed)",
                    "messages": [], "completion_status": "skipped"}
        p.subagent_type = claimed.subagent_type
        p.prompt = claimed.prompt
        task_store = TaskStore(redis, run_id=p.blackboard_task_id, ttl=3600)
    try:
        runtime_suite, deps = build_runtime_and_deps(p)
        result = await asyncio.to_thread(_run_subagent_sync, runtime_suite, deps, p)
        if task_store is not None:
            status = "done" if result.get("success") else "failed"
            await task_store.set_status(
                p.subagent_task_id, status, result=str(result.get("content", ""))[:280]
            )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("background subagent failed: %s", exc)
        if task_store is not None:
            await task_store.set_status(p.subagent_task_id, "failed", result=str(exc)[:280])
        return {
            "success": False,
            "content": f"background subagent failed: {exc}",
            "messages": [],
            "completion_status": "error",
        }
    finally:
        handle = getattr(deps, "blackboard", None) if deps is not None else None
        if handle is not None:
            from minder.core.blackboard.provision import teardown_run_blackboard

            teardown_run_blackboard(handle)
        if redis is not None:
            await redis.aclose()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/core/tasks/test_worker_blackboard_task.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add minder/core/tasks/payload.py minder/core/tasks/tasks.py \
        tests/core/tasks/test_worker_blackboard_task.py
git commit -m "feat(tasks): worker claims + reads delegated task from blackboard"
```

---

### Task 6: Tool schemas + `subagent` tool description

**Files:**
- Modify: `minder/core/agents/components/schemas/builtin/orchestration_tools.py`
- Modify: `minder/core/agents/subagents/task_tool.py`
- Create: `minder/core/agents/prompts/templates/tools/tool-subagent.md`
- Create: `minder/core/agents/prompts/templates/tools/tool-get-subagent-output.md`
- Delete: `minder/core/agents/prompts/templates/tools/tool-solve.md`
- Delete: `minder/core/agents/prompts/templates/tools/tool-get-solve-result.md`
- Test: `tests/core/agents/test_subagent_schema.py`

**Interfaces:**
- Consumes: `load_tool_description`.
- Produces: schema dicts named `subagent` (params: `tasks` array of `{subagent_type, prompt}`, required `["tasks"]`) and `get_subagent_output` (params: `job_id` required, optional `block`, `timeout`). Removes `solve` and `get_solve_result` schemas.

- [ ] **Step 1: Write the failing test**

Create `tests/core/agents/test_subagent_schema.py`:

```python
from minder.core.agents.components.schemas.builtin.orchestration_tools import SCHEMAS


def _names():
    return {s["function"]["name"] for s in SCHEMAS}


def test_subagent_schema_present_and_shaped():
    assert "subagent" in _names()
    sub = next(s for s in SCHEMAS if s["function"]["name"] == "subagent")
    props = sub["function"]["parameters"]["properties"]
    assert "tasks" in props and props["tasks"]["type"] == "array"
    assert sub["function"]["parameters"]["required"] == ["tasks"]


def test_get_subagent_output_schema_present():
    assert "get_subagent_output" in _names()


def test_legacy_solver_schemas_removed():
    assert "solve" not in _names()
    assert "get_solve_result" not in _names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/agents/test_subagent_schema.py -v`
Expected: FAIL (`subagent` not in names; `solve` still present).

- [ ] **Step 3: Replace the schemas**

In `minder/core/agents/components/schemas/builtin/orchestration_tools.py`, delete the two dicts for `solve` and `get_solve_result` (from the `# ===== Unified Solver Tools ...` comment through the closing `},` of the `get_solve_result` schema, i.e. the block ending at line ~106). Replace with:

```python
    # ===== Unified subagent tool (blackboard task channel) =====
    {
        "type": "function",
        "function": {
            "name": "subagent",
            "description": load_tool_description("subagent"),
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "description": (
                            "One or more independent tasks to delegate. Each runs as "
                            "its own subagent on a worker; all share one blackboard so "
                            "they read each other's committed notes. A single "
                            "delegation is just a one-element list."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "subagent_type": {
                                    "type": "string",
                                    "description": "Which subagent type runs this task.",
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": (
                                        "Full self-contained instructions; the subagent "
                                        "has no access to conversation history."
                                    ),
                                },
                            },
                            "required": ["subagent_type", "prompt"],
                        },
                    },
                },
                "required": ["tasks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_subagent_output",
            "description": load_tool_description("get_subagent_output"),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job_id returned by subagent.",
                    },
                    "block": {
                        "type": "boolean",
                        "description": "Wait for all tasks to finish. False for a status poll.",
                        "default": True,
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum wait time in milliseconds (max 600000).",
                        "default": 30000,
                        "maximum": 600000,
                    },
                },
                "required": ["job_id"],
            },
        },
    },
```

- [ ] **Step 4: Create the tool-description markdown**

Create `minder/core/agents/prompts/templates/tools/tool-subagent.md`:

```markdown
Delegate one or more independent tasks to ephemeral subagents.

Each task in `tasks` runs as its own subagent on a background worker, in an
isolated context, and writes its findings back to a shared blackboard. All tasks
in one call share that blackboard, so a later wave can build on what an earlier
wave committed.

Use this to hand off self-contained work: research, code exploration, review, or
a focused change. Put everything the subagent needs in `prompt` — it cannot see
the conversation. Pass several tasks at once to run them concurrently.

Tasks are independent (no dependency ordering). When you need step B to use step
A's result, run A first, collect it with `get_subagent_output`, then issue B.

Returns a `job_id`. Requires Redis and a running `minder-worker`.
```

Create `minder/core/agents/prompts/templates/tools/tool-get-subagent-output.md`:

```markdown
Collect the results of a `subagent` job by its `job_id`.

Returns each task's status (pending, claimed, done, failed) and a digest of the
notes the subagents wrote to the shared blackboard. By default it blocks until
every task finishes; pass `block: false` for a non-blocking status poll.
```

- [ ] **Step 5: Delete the obsolete descriptions and update the task tool**

```bash
git rm minder/core/agents/prompts/templates/tools/tool-solve.md \
       minder/core/agents/prompts/templates/tools/tool-get-solve-result.md
```

In `minder/core/agents/subagents/task_tool.py`, change:

```python
TASK_TOOL_NAME = "spawn_subagent"
```

to:

```python
TASK_TOOL_NAME = "subagent"
```

and delete the entire `## Strategy` section (the `- \`direct\``, `- \`divide\``, `- \`parallel\`` bullet block) from `TASK_TOOL_DESCRIPTION`, since strategy no longer exists.

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/core/agents/test_subagent_schema.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add minder/core/agents/components/schemas/builtin/orchestration_tools.py \
        minder/core/agents/subagents/task_tool.py \
        minder/core/agents/prompts/templates/tools/tool-subagent.md \
        minder/core/agents/prompts/templates/tools/tool-get-subagent-output.md \
        tests/core/agents/test_subagent_schema.py
git commit -m "feat(schemas): replace solve/spawn_subagent schemas with unified subagent tool"
```

---

### Task 7: Rewire the registry to the unified handlers

**Files:**
- Modify: `minder/core/context_engineering/tools/registry_mixins/orchestration_ops.py` (full rewrite)
- Delete: `minder/core/context_engineering/tools/registry_mixins/subagent_ops.py`
- Modify: `minder/core/context_engineering/tools/registry_mixins/__init__.py`
- Modify: `minder/core/context_engineering/tools/registry.py`
- Test: `tests/core/context_engineering/test_registry_subagent_routing.py`

**Interfaces:**
- Consumes: `build_subagent_orchestrator`, `execute_subagent_fanout`, `execute_get_subagent_output` (Task 4).
- Produces on `ToolRegistry`: `_get_subagent_orchestrator(context) -> orchestrator | None`, `_execute_subagent_fanout(arguments, context) -> dict`, `_execute_get_subagent_output(arguments, context) -> dict`, `_get_repo_dir() -> str`. The handler map routes `"subagent"` and `"get_subagent_output"`; `"spawn_subagent"`, `"solve"`, `"get_solve_result"` are gone.

- [ ] **Step 1: Write the failing test**

Create `tests/core/context_engineering/test_registry_subagent_routing.py`:

```python
def test_registry_routes_unified_subagent_tools(monkeypatch):
    import minder.core.context_engineering.tools.registry as reg_mod

    reg = reg_mod.ToolRegistry.__new__(reg_mod.ToolRegistry)
    reg._subagent_manager = None
    reg._app_config = None
    reg.file_ops = None
    handlers = reg_mod.ToolRegistry._build_handlers(reg) if hasattr(
        reg_mod.ToolRegistry, "_build_handlers"
    ) else None
    # Fallback: assert the source no longer references removed tool names.
    src = __import__("inspect").getsource(reg_mod)
    assert '"subagent": self._execute_subagent_fanout' in src
    assert '"get_subagent_output": self._execute_get_subagent_output' in src
    assert '"solve"' not in src and '"get_solve_result"' not in src
    assert "spawn_subagent" not in src
```

Note: this test reads the registry source to assert the routing table changed; it avoids constructing the full registry (which needs many services). If `registry.py` factors handler construction into a `_build_handlers` method, prefer asserting on the returned dict keys instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/context_engineering/test_registry_subagent_routing.py -v`
Expected: FAIL (source still contains `"solve"` / `spawn_subagent`).

- [ ] **Step 3: Rewrite `orchestration_ops.py`**

Replace the entire contents of `minder/core/context_engineering/tools/registry_mixins/orchestration_ops.py` with:

```python
"""Unified ``subagent`` fan-out orchestration for the tool registry."""

from __future__ import annotations

from typing import Any


class OrchestrationOpsMixin:
    """Lazily-built subagent orchestrator and its two tool handlers."""

    def _get_repo_dir(self) -> str:
        """Return the run's repo/working directory, defaulting to '.'."""
        return (
            str(self.file_ops.working_dir)
            if self.file_ops and getattr(self.file_ops, "working_dir", None)
            else "."
        )

    def _get_subagent_orchestrator(self, context: Any = None) -> Any:
        """Build (once per run) the SubagentOrchestrator from this run's context.

        Requires the run's TaskIQClient (attached to the subagent manager via
        ``attach_task_client``). Returns None when no task client is available —
        subagent delegation needs a running worker + Redis.
        """
        if getattr(self, "_subagent_orchestrator", None) is not None:
            return self._subagent_orchestrator
        mgr = self._subagent_manager
        task_client = getattr(mgr, "_task_client", None) if mgr is not None else None
        if task_client is None:
            return None

        from minder.core.context_engineering.tools.implementations.send_table_tool import (
            resolve_session,
        )
        from minder.core.subagents.tools import build_subagent_orchestrator

        ui_callback = getattr(context, "ui_callback", None) if context else None
        progress_cb = None
        if ui_callback is not None and hasattr(ui_callback, "on_solver_event"):
            progress_cb = lambda stage, data: ui_callback.on_solver_event(  # noqa: E731
                "subagent", stage, data
            )

        session_id, working_dir = resolve_session(context)
        session_id = session_id or ""
        working_dir = working_dir or self._get_repo_dir()
        _sess_mgr = getattr(context, "session_manager", None) if context else None
        _current = getattr(_sess_mgr, "current_session", None) if _sess_mgr else None
        owner_id = (getattr(_current, "owner_id", None) or "") if _current else ""

        self._subagent_orchestrator = build_subagent_orchestrator(
            task_client=task_client,
            config=self._app_config,
            owner_id=owner_id,
            session_id=session_id,
            working_dir=str(working_dir),
            progress_cb=progress_cb,
        )
        return self._subagent_orchestrator

    def _execute_subagent_fanout(
        self, arguments: dict[str, Any], context: Any = None
    ) -> dict[str, Any]:
        """Dispatch the ``subagent`` tool: write tasks + fan workers out."""
        orch = self._get_subagent_orchestrator(context)
        if orch is None:
            return {
                "success": False,
                "error": "Subagent delegation unavailable (no task client). "
                "Requires a running TaskIQ worker + Redis.",
                "output": None,
            }
        from minder.core.subagents.tools import execute_subagent_fanout

        return execute_subagent_fanout(arguments, orch)

    def _execute_get_subagent_output(
        self, arguments: dict[str, Any], context: Any = None
    ) -> dict[str, Any]:
        """Dispatch ``get_subagent_output``: collect statuses + notes digest."""
        orch = self._get_subagent_orchestrator(context)
        if orch is None:
            return {
                "success": False,
                "error": "Subagent delegation unavailable (no task client).",
                "output": None,
            }
        from minder.core.subagents.tools import execute_get_subagent_output

        return execute_get_subagent_output(arguments, orch)
```

- [ ] **Step 4: Delete `subagent_ops.py` and update the mixin package**

```bash
git rm minder/core/context_engineering/tools/registry_mixins/subagent_ops.py
```

In `minder/core/context_engineering/tools/registry_mixins/__init__.py`, remove the `SubagentOpsMixin` import, its `__all__` entry, and its docstring bullet. The file's import/`__all__` should read:

```python
from .inline_tools import InlineToolsMixin
from .orchestration_ops import OrchestrationOpsMixin

__all__ = ["OrchestrationOpsMixin", "InlineToolsMixin"]
```

(Keep whatever other mixins the file already exports; only `SubagentOpsMixin` is removed.)

- [ ] **Step 5: Update `registry.py`**

In `minder/core/context_engineering/tools/registry.py`:

1. Remove `SubagentOpsMixin` from the import block (line ~75) and from the class bases (line ~80: `class ToolRegistry(SubagentOpsMixin, OrchestrationOpsMixin, InlineToolsMixin):` → `class ToolRegistry(OrchestrationOpsMixin, InlineToolsMixin):`).
2. In the handler map (lines ~193-199), replace:

```python
            # Subagent spawning tool
            "spawn_subagent": self._execute_spawn_subagent,
            # Get output from background subagent
            "get_subagent_output": self._get_subagent_output,
            # Unified solver tools (divide + parallel behind a strategy param)
            "solve": self._execute_solve,
            "get_solve_result": self._execute_get_solve_result,
```

with:

```python
            # Unified subagent delegation (blackboard task channel)
            "subagent": self._execute_subagent_fanout,
            "get_subagent_output": self._execute_get_subagent_output,
```

3. In the dispatch block (lines ~432-452), remove the `if tool_name == "spawn_subagent":` branch entirely, and remove `"solve"` and `"get_solve_result"` from the context-passing `elif tool_name in { ... }` set. Add `"subagent"` and `"get_subagent_output"` to that same set so they receive `context`:

```python
            elif tool_name in {
                "write_file",
                "edit_file",
                "read_file",
                "run_command",
                "batch_tool",
                "present_plan",
                "list_sessions",
                "get_session_history",
                "send_image",
                "send_editable_table",
                "send_table",
                "list_artifact_images",
                "read_artifact_image",
                "NOTE",
                "subagent",
                "get_subagent_output",
                "write_todos",
                "update_todo",
                "complete_todo",
                "clear_todos",
            }:
                result = handler(arguments, context)
```

4. In the `build_context(...)` call (near line ~424), remove the `divide_orchestrator=divide_orchestrator,` and `parallel_orchestrator=parallel_orchestrator,` keyword arguments and any local variables that computed them. Grep to confirm none remain:

```bash
grep -n "divide_orchestrator\|parallel_orchestrator" minder/core/context_engineering/tools/registry.py
```

Expected after edits: no matches.

- [ ] **Step 6: Run the routing test + import check**

Run: `uv run pytest tests/core/context_engineering/test_registry_subagent_routing.py -v`
Expected: PASS.

Run: `uv run python -c "import minder.core.context_engineering.tools.registry"`
Expected: no ImportError.

- [ ] **Step 7: Commit**

```bash
git add minder/core/context_engineering/tools/registry_mixins/ \
        minder/core/context_engineering/tools/registry.py \
        tests/core/context_engineering/test_registry_subagent_routing.py
git commit -m "refactor(registry): route unified subagent tools, drop solve/spawn_subagent"
```

---

### Task 8: Delete dead divide/parallel code + purge references

**Files:**
- Delete: `minder/core/parallel/` (whole dir)
- Delete: `minder/core/divide/decompose.py`, `minder/core/divide/scheduler.py`
- Modify: `minder/core/divide/orchestrator.py`, `minder/core/divide/tools.py`, `minder/core/divide/__init__.py` (remove or reduce — see below)
- Modify: `build_context` provider (wherever `divide_orchestrator`/`parallel_orchestrator` were injected)
- Delete: obsolete tests `tests/test_parallel_*.py`, `tests/test_divide_redecompose.py`, `tests/test_subagent_dispatch.py` (dispatch-strategy test)

**Interfaces:**
- Produces: a codebase with no remaining importers of `minder.core.parallel`, `minder.core.divide.decompose`, or `minder.core.divide.scheduler`.

- [ ] **Step 1: Find every reference**

Run:

```bash
grep -rn "core\.parallel\|from minder.core.parallel" minder tests --include="*.py"
grep -rn "core\.divide\|from minder.core.divide" minder tests --include="*.py"
grep -rn "divide_orchestrator\|parallel_orchestrator\|_dispatch_via_orchestrator\|execute_solve\|get_solve_result\|_execute_spawn_subagent\|spawn_subagent" minder tests --include="*.py"
```

Record every hit; each must be removed or repointed by the end of this task.

- [ ] **Step 2: Delete parallel + divide decomposition/scheduler**

```bash
git rm -r minder/core/parallel
git rm minder/core/divide/decompose.py minder/core/divide/scheduler.py
```

- [ ] **Step 3: Reduce the divide package**

`minder/core/divide/orchestrator.py` and `tools.py` import `decompose`/`schedule`, which are now gone. The divide package no longer has a tool entry point (Task 7 removed its handlers). Delete the remaining divide modules that only served the old flow:

```bash
git rm minder/core/divide/orchestrator.py minder/core/divide/tools.py
```

Keep `minder/core/divide/models.py` ONLY if `grep -rn "divide.models\|DivideJob\|DivideTask" minder --include="*.py"` shows a live importer outside the deleted files; otherwise:

```bash
git rm minder/core/divide/models.py
```

If the whole `minder/core/divide/` directory is now empty except `__init__.py`, remove it:

```bash
git rm -r minder/core/divide
```

- [ ] **Step 4: Remove orchestrator injection from context building**

From Task 7 the registry no longer passes `divide_orchestrator`/`parallel_orchestrator`. Now remove them at the source. Locate the context object + any builder that still sets them:

```bash
grep -rn "divide_orchestrator\|parallel_orchestrator" minder --include="*.py"
```

For each hit (e.g. a `ToolExecutionContext` dataclass field, or a `build_context` helper), delete the field/parameter and its assignment. Re-run the grep; expected: no matches.

- [ ] **Step 5: Delete obsolete tests**

```bash
git rm tests/test_parallel_real.py tests/test_parallel_tool_display.py \
       tests/test_parallel_tool_execution.py tests/test_parallel_tools.py \
       tests/test_parallel_waves.py tests/test_divide_redecompose.py \
       tests/test_subagent_dispatch.py
```

Then grep the remaining tests for stragglers referencing removed symbols:

```bash
grep -rn "spawn_subagent\|solve\|divide\|parallel" tests --include="*.py"
```

For any remaining hit that references removed behaviour (e.g. `strategy=` on the old tool), delete or update that test to the new `subagent(tasks=[...])` shape.

- [ ] **Step 6: Verify nothing imports the deleted modules**

Run:

```bash
uv run python -c "import minder.cli"
grep -rn "core\.parallel\|core\.divide\|_execute_spawn_subagent\|_execute_solve" minder --include="*.py"
```

Expected: import succeeds; grep returns no matches.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: delete divide/parallel machinery superseded by unified subagent"
```

---

### Task 9: Update prompt guidance for the unified concept

**Files:**
- Modify: `minder/core/agents/prompts/templates/system/main/main-subagent-guide.md`
- Modify: `minder/core/agents/prompts/templates/system/main/main-available-tools.md`
- Modify: `minder/core/agents/prompts/templates/system/main/main-tool-selection.md`
- Modify: `minder/core/agents/prompts/templates/system/main/main-action-safety.md`
- Modify: `minder/core/agents/prompts/templates/system/main/main-tone-and-style.md`

**Interfaces:** None (prompt text only). No tables (project rule).

- [ ] **Step 1: Find every prompt mention of the old concepts**

Run:

```bash
grep -rln "spawn_subagent\|solve\|get_solve_result\|divide\|parallel\|strategy" \
     minder/core/agents/prompts/templates/system
```

- [ ] **Step 2: Rewrite the subagent guide**

In `main-subagent-guide.md`, remove any `spawn_subagent`, `strategy`, `divide`, `parallel`, `solve` wording and describe the single tool in prose (no tables). Ensure it explains:

- Call `subagent(tasks=[{subagent_type, prompt}, ...])` to delegate; one element for a single hand-off, several for concurrent independent tasks.
- Tasks share one blackboard and write notes back; there is no dependency ordering — run a wave, collect with `get_subagent_output(job_id)`, then issue the next wave when step B needs step A's result.
- Delegation requires Redis + a running `minder-worker`.

- [ ] **Step 3: Fix the remaining sections**

In `main-available-tools.md`, `main-tool-selection.md`, `main-action-safety.md`, and `main-tone-and-style.md`, replace each reference to `spawn_subagent` / `solve` / `get_solve_result` / strategy-based delegation with the `subagent` / `get_subagent_output` pair. Keep edits minimal and in prose.

- [ ] **Step 4: Verify no stale references remain**

Run:

```bash
grep -rn "spawn_subagent\|get_solve_result\|\bsolve\b\|strategy=\"divide\"\|strategy=\"parallel\"" \
     minder/core/agents/prompts/templates/system
```

Expected: no matches (a bare word "parallel" describing concurrency is fine; the tool/strategy references are gone).

- [ ] **Step 5: Commit**

```bash
git add minder/core/agents/prompts/templates/system/main/
git commit -m "docs(prompts): describe the unified subagent tool, drop divide/parallel/solve"
```

---

### Task 10: Full verification + real end-to-end

**Files:** none (verification only).

- [ ] **Step 1: Run the whole unit suite**

Run: `make test` (or `uv run pytest`)
Expected: PASS. Fix any failure from a missed reference before proceeding.

- [ ] **Step 2: Lint + typecheck**

Run: `make check`
Expected: Black clean, Ruff clean, mypy clean. Fix issues inline.

- [ ] **Step 3: Real end-to-end (per CLAUDE.md — REQUIRED)**

In three terminals with `OPENAI_API_KEY` exported and `MINDER_REDIS_URL` set:

```bash
# 1) Redis
redis-server

# 2) Worker
uv run minder-worker

# 3) Drive the CLI with a real fan-out
export OPENAI_API_KEY="...";  export MINDER_REDIS_URL="redis://localhost:6379/0"
uv run minder -p "Use the subagent tool to run two independent tasks: (a) a code_explorer that lists the top-level packages under minder/core, and (b) a code_explorer that finds where the blackboard TaskStore is defined. Then call get_subagent_output on the returned job_id and summarize both results."
```

Expected: the agent calls `subagent` once with two tasks, both run on the worker, and `get_subagent_output` returns both task statuses as `done` with a notes digest. Confirm no `solve` / `spawn_subagent` tool appears and no traceback in the worker log.

- [ ] **Step 4: Confirm the blackboard carried the tasks**

While the run is in flight (or from the worker log), verify the task channel was populated:

```bash
redis-cli --scan --pattern 'minder:bb:sa_*:tasks' | head
```

Expected: at least one `minder:bb:sa_<job>:tasks` hash key exists, confirming tasks were sourced from the blackboard.

- [ ] **Step 5: Final commit (if any verification fixes were made)**

```bash
git add -A
git commit -m "test: verify unified subagent end-to-end"
```

---

## Self-Review

**Spec coverage:**
- One `subagent` concept, tools 4→2 — Tasks 6, 7 (schemas + routing).
- Blackboard as task source (`Task` + `TaskStore`, worker reads task) — Tasks 1, 2, 5.
- Results written back as notes / collected via digest — Tasks 3 (`collect_async` renders digest), 5 (worker's blackboard handle writes notes).
- Flat, no dependencies; agent orchestrates waves — Task 3 (no scheduler), Task 9 (guidance).
- Always-worker, Redis required — Tasks 4, 5, 7 (no in-process path; `None` when no task client).
- Drop parallel/judge, divide decomposer + scheduler — Task 8 deletes them.
- Testing (unit + real E2E) — every task has unit tests; Task 10 does the real run.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; delete steps give exact `git rm` commands and verifying greps.

**Type consistency:** `Task` fields (`id, subagent_type, prompt, status, result, ts`) are identical across models.py, TaskStore, orchestrator, worker, and schema `items`. `SubagentOrchestrator.start(tasks: list[dict])` matches `execute_subagent_fanout` passing `arguments["tasks"]`. Job record keys (`job_id, bb_id, task_ids, status`) are written in `start_async` and read in `collect_async` + Task 3 tests. `subagent_task_id` added in Task 5 payload is set in Task 3's `start_async` and read in Task 5's worker — consistent.
