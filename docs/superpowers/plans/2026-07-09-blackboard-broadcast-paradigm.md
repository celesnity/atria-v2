# Blackboard Broadcast Paradigm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the master-slave `subagent(tasks=[{subagent_type, prompt}])` dispatch with the paper's broadcast-request / voluntary-response paradigm (arXiv:2510.01285): the main agent posts an un-addressed request, each helper autonomously bids on it, volunteers write to a separate response board, and a web-ui viewer shows the bid roster.

**Architecture:** A `request_help(prompt)` tool writes a `Request` to the blackboard. The orchestrator runs an independent cheap-LLM bid per helper (each sees only its own capability profile), enqueues the existing TaskIQ worker path for volunteers only, and workers write answers to a new `ResponseStore` (board `β_r`, separate from the shared note channel `β`). `get_help_responses(request_id)` collects responses + bids + note digest. Bid/request/response events are published to Redis and bridged to the web-ui over WebSocket, where a `BlackboardPage` renders them.

**Tech Stack:** Python 3, asyncio, `redis.asyncio`, TaskIQ, pydantic; React + TypeScript + Vite + Zustand (`web-ui/`); pytest.

## Global Constraints

- Line length 100 chars (Black + Ruff); type hints on public APIs (mypy strict); Google-style docstrings.
- No `subagent_type` may be chosen by the tool caller — the bid derives which helpers run.
- Fail-open on blackboard/redis errors (return status strings / `""`), fail-**closed** on bid errors (no volunteer). Never crash the agent loop.
- Reuse the existing cheap-model verifier chain via `build_verify_llm(config)` for bids — do not resolve the main-agent model.
- Redis key namespace: `atria:bb:{run_id}:...` where `run_id = "sa_" + job_id`.
- Tests run with `uv run --no-sync pytest`. Real e2e uses `OPENAI_API_KEY` + proxy from repo `.env`, redis + `atria-worker` live (per `CLAUDE.md`).
- Frontend build: `cd web-ui && npm run build` → outputs to `atria/web/static/` (committed).
- Branch: `feat/blackboard-broadcast-paradigm` (already checked out; spec committed there).

---

## File Structure

**New backend files:**
- `atria/core/blackboard/response_store.py` — `ResponseStore` + `BidStore` (Redis hashes for `β_r` and the bid roster).
- `atria/core/blackboard/board_events.py` — `publish_board_event(redis, run_id, kind, payload)` for request/bid/response viewer events.
- `atria/core/subagents/bid.py` — `run_bids(...)`: concurrent, independent, fail-closed per-helper self-assessment.

**Modified backend files:**
- `atria/core/blackboard/models.py` — add `Request`, `Response`, `Bid` dataclasses.
- `atria/core/agents/subagents/specs.py` — add `capability_profile` to `SubAgentSpec`.
- `atria/core/agents/subagents/manager/manager.py` — add `capability_profile` to `AgentConfig`.
- `atria/core/agents/subagents/manager/registration.py` — populate `capability_profile` in `get_agent_configs()`.
- `atria/core/agents/subagents/agents/{module_worker,planner,web_generator}.py` — add profiles.
- `atria/core/tasks/payload.py` — add `bid_confidence: float = 0.0`.
- `atria/core/tasks/tasks.py` — worker writes a `Response` to `ResponseStore`.
- `atria/core/subagents/orchestrator.py` — request flow: write Request → bid → enqueue volunteers → collect responses+bids.
- `atria/core/subagents/tools.py` — `build_subagent_orchestrator` gains `helper_profiles`; `execute_request_help` / `execute_get_help_responses`.
- `atria/core/agents/subagents/task_tool.py` — `request_help` schema.
- `atria/core/context_engineering/tools/registry.py` + `registry_mixins/orchestration_ops.py` — dispatch new tool names, pass profiles.
- `atria/web/blackboard_subscriber.py` — forward `atria:bb:*:board` events.

**New frontend files:**
- `web-ui/src/stores/blackboardStore.ts` — Zustand store for requests/bids/responses.
- `web-ui/src/pages/BlackboardPage.tsx` — the viewer.

**Modified frontend files:**
- `web-ui/src/api/websocket.ts` (no change needed — generic `{type,data}` router) ; `web-ui/src/App.tsx` — route + side-effect import; `web-ui/src/types/index.ts` — WS type literals.

---

## Phase 1 — Data model & stores

### Task 1: Request / Response / Bid models

**Files:**
- Modify: `atria/core/blackboard/models.py`
- Test: `tests/core/blackboard/test_broadcast_models.py`

**Interfaces:**
- Produces: `Request(id, prompt, status, ts)`, `Response(request_id, responder, content, confidence, ts)`, `Bid(request_id, responder, volunteered, reason, confidence, ts)` — all frozen dataclasses with `to_dict()` / `from_dict()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/blackboard/test_broadcast_models.py
from atria.core.blackboard.models import Bid, Request, Response


def test_request_roundtrip():
    r = Request(id="j1", prompt="find the auth module", status="open", ts=1.0)
    assert Request.from_dict(r.to_dict()) == r


def test_response_roundtrip():
    r = Response(request_id="j1", responder="Planner", content="see auth.py:12",
                 confidence=0.8, ts=2.0)
    assert Response.from_dict(r.to_dict()) == r


def test_bid_roundtrip_and_decline():
    b = Bid(request_id="j1", responder="Web-Generator", volunteered=False,
            reason="no UI work needed", confidence=0.1, ts=3.0)
    d = b.to_dict()
    assert d["volunteered"] is False
    assert Bid.from_dict(d) == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/core/blackboard/test_broadcast_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Request'`.

- [ ] **Step 3: Add the models**

Append to `atria/core/blackboard/models.py` (after the existing `Task` block):

```python
REQUEST_STATUSES: tuple[str, ...] = ("open", "answered", "closed")


@dataclass(frozen=True)
class Request:
    """One un-addressed request the main agent posts to board β (paper §3)."""

    id: str
    prompt: str
    status: str = "open"
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"id": self.id, "prompt": self.prompt,
                "status": self.status, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Request":
        return cls(id=d["id"], prompt=d["prompt"],
                   status=d.get("status", "open"), ts=float(d.get("ts", 0.0)))


@dataclass(frozen=True)
class Response:
    """One helper's answer on the response board β_r (exclusive to the main agent)."""

    request_id: str
    responder: str
    content: str
    confidence: float = 0.0
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"request_id": self.request_id, "responder": self.responder,
                "content": self.content, "confidence": self.confidence, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Response":
        return cls(request_id=d["request_id"], responder=d["responder"],
                   content=d["content"], confidence=float(d.get("confidence", 0.0)),
                   ts=float(d.get("ts", 0.0)))


@dataclass(frozen=True)
class Bid:
    """One helper's autonomous self-assessment of a request (for telemetry/viewer)."""

    request_id: str
    responder: str
    volunteered: bool
    reason: str = ""
    confidence: float = 0.0
    ts: float = 0.0

    def to_dict(self) -> dict:
        return {"request_id": self.request_id, "responder": self.responder,
                "volunteered": self.volunteered, "reason": self.reason,
                "confidence": self.confidence, "ts": self.ts}

    @classmethod
    def from_dict(cls, d: dict) -> "Bid":
        return cls(request_id=d["request_id"], responder=d["responder"],
                   volunteered=bool(d["volunteered"]), reason=d.get("reason", ""),
                   confidence=float(d.get("confidence", 0.0)), ts=float(d.get("ts", 0.0)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/core/blackboard/test_broadcast_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add atria/core/blackboard/models.py tests/core/blackboard/test_broadcast_models.py
git commit -m "feat(blackboard): Request/Response/Bid models for broadcast paradigm"
```

---

### Task 2: ResponseStore + BidStore

**Files:**
- Create: `atria/core/blackboard/response_store.py`
- Test: `tests/core/blackboard/test_response_store.py`

**Interfaces:**
- Consumes: `Response`, `Bid` (Task 1); a fakeredis-like async client.
- Produces: `ResponseStore(redis, run_id, ttl)` with `async add(list[Response])`, `async all() -> list[Response]`; `BidStore(redis, run_id, ttl)` with `async add(list[Bid])`, `async all() -> list[Bid]`. Keys `atria:bb:{run_id}:responses` and `atria:bb:{run_id}:bids`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/blackboard/test_response_store.py
import pytest

from atria.core.blackboard.models import Bid, Response
from atria.core.blackboard.response_store import BidStore, ResponseStore


class FakeRedis:
    def __init__(self):
        self.h = {}
    async def hset(self, key, mapping=None):
        self.h.setdefault(key, {}).update(mapping or {})
    async def expire(self, key, ttl):
        return True
    async def hgetall(self, key):
        return {k.encode(): v.encode() for k, v in self.h.get(key, {}).items()}


@pytest.mark.asyncio
async def test_response_store_roundtrip():
    r = FakeRedis()
    s = ResponseStore(r, run_id="sa_1", ttl=60)
    await s.add([Response(request_id="sa_1", responder="Planner", content="x",
                          confidence=0.7, ts=1.0)])
    got = await s.all()
    assert [x.responder for x in got] == ["Planner"]
    assert got[0].confidence == 0.7


@pytest.mark.asyncio
async def test_bid_store_roundtrip():
    r = FakeRedis()
    s = BidStore(r, run_id="sa_1", ttl=60)
    await s.add([Bid(request_id="sa_1", responder="Web-Generator", volunteered=False,
                     reason="n/a", confidence=0.0, ts=1.0)])
    got = await s.all()
    assert got[0].volunteered is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/core/blackboard/test_response_store.py -v`
Expected: FAIL with `ModuleNotFoundError: ... response_store`.

- [ ] **Step 3: Create the store**

```python
# atria/core/blackboard/response_store.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/core/blackboard/test_response_store.py -v`
Expected: PASS (2 tests). If `pytest-asyncio` markers error, confirm the repo's existing async tests pattern (other `tests/core/blackboard/` files use `@pytest.mark.asyncio`).

- [ ] **Step 5: Commit**

```bash
git add atria/core/blackboard/response_store.py tests/core/blackboard/test_response_store.py
git commit -m "feat(blackboard): ResponseStore + BidStore for response board and bid roster"
```

---

## Phase 2 — Capability profiles

### Task 3: capability_profile on specs, AgentConfig, and the three helpers

**Files:**
- Modify: `atria/core/agents/subagents/specs.py:9-16` (add field)
- Modify: `atria/core/agents/subagents/manager/manager.py:29-37` (add field)
- Modify: `atria/core/agents/subagents/manager/registration.py:82-101` (populate)
- Modify: `atria/core/agents/subagents/agents/module_worker.py`, `planner.py`, `web_generator.py`
- Test: `tests/core/agents/subagents/test_capability_profiles.py`

**Interfaces:**
- Produces: `AgentConfig.capability_profile: str | None`; `SubAgentSpec` optional `capability_profile: str`. `get_agent_configs()` returns configs whose `.capability_profile` is populated from the spec (empty for `ask-user`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/agents/subagents/test_capability_profiles.py
from atria.core.agents.subagents.agents.module_worker import MODULE_WORKER_SUBAGENT


def test_module_worker_has_profile():
    assert MODULE_WORKER_SUBAGENT.get("capability_profile")
    assert "module" in MODULE_WORKER_SUBAGENT["capability_profile"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/core/agents/subagents/test_capability_profiles.py -v`
Expected: FAIL (`capability_profile` key missing).

- [ ] **Step 3a: Add field to `SubAgentSpec`**

In `atria/core/agents/subagents/specs.py`, inside the `SubAgentSpec(TypedDict)` block, add after `system_prompt: str`:

```python
    capability_profile: NotRequired[str]
```

- [ ] **Step 3b: Add field to `AgentConfig`**

In `atria/core/agents/subagents/manager/manager.py`, in the `AgentConfig` dataclass (after `model: str | None = None`):

```python
    capability_profile: str | None = None
```

- [ ] **Step 3c: Populate in `get_agent_configs()`**

In `atria/core/agents/subagents/manager/registration.py`, where each `AgentConfig` is built from a spec (around line 95-97, alongside `description=spec["description"]`), add:

```python
            capability_profile=spec.get("capability_profile"),
```

(Apply to both the builtin-spec branch and the custom-agent branch if present — search the function for every `AgentConfig(` constructor and add the kwarg. Custom agents without a profile pass `None`.)

- [ ] **Step 3d: Add the three profiles**

`module_worker.py` — add to `MODULE_WORKER_SUBAGENT` dict:

```python
    "capability_profile": (
        "Implements a focused change or task within a single module using that "
        "module's documented commands (run scripts, invoke skills, edit files)."
    ),
```

`planner.py` — add to the planner spec dict:

```python
    "capability_profile": (
        "Explores and maps the codebase: locates definitions, traces callers, "
        "finds patterns, and reports where/how things are implemented."
    ),
```

`web_generator.py` — add to the web-generator spec dict:

```python
    "capability_profile": (
        "Builds responsive web UIs (React, TypeScript, Tailwind): components, "
        "pages, and frontend wiring."
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/core/agents/subagents/test_capability_profiles.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add atria/core/agents/subagents/specs.py atria/core/agents/subagents/manager/manager.py atria/core/agents/subagents/manager/registration.py atria/core/agents/subagents/agents/module_worker.py atria/core/agents/subagents/agents/planner.py atria/core/agents/subagents/agents/web_generator.py tests/core/agents/subagents/test_capability_profiles.py
git commit -m "feat(subagents): capability_profile on specs + AgentConfig + helpers"
```

---

## Phase 3 — Bid engine

### Task 4: `run_bids` — concurrent, independent, fail-closed

**Files:**
- Create: `atria/core/subagents/bid.py`
- Test: `tests/core/subagents/test_bid.py`

**Interfaces:**
- Consumes: `Bid` (Task 1); a synchronous `verify_llm(system, user) -> str` (from `build_verify_llm`, may be `None`).
- Produces:
  `async def run_bids(request_id: str, prompt: str, profiles: list[tuple[str, str]], verify_llm, *, max_helpers: int, now: float) -> list[Bid]` — one `Bid` per profile, evaluated independently (each call sees only its own profile), concurrent via `asyncio.to_thread`, fail-closed (`verify_llm is None` or raises/empty → `volunteered=False`). Only up to `max_helpers` volunteers are marked `volunteered=True` (highest confidence first); the rest are recorded as declines.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/subagents/test_bid.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/core/subagents/test_bid.py -v`
Expected: FAIL (`ModuleNotFoundError: ... bid`).

- [ ] **Step 3: Implement the bid engine**

```python
# atria/core/subagents/bid.py
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

from atria.core.blackboard.models import Bid

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/core/subagents/test_bid.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add atria/core/subagents/bid.py tests/core/subagents/test_bid.py
git commit -m "feat(subagents): autonomous per-helper bid engine (fail-closed, capped)"
```

---

## Phase 4 — Orchestrator request flow

### Task 5: rewrite `SubagentOrchestrator` to the request/bid/collect flow

**Files:**
- Modify: `atria/core/subagents/orchestrator.py` (whole file — replace task-list flow with request flow)
- Test: `tests/core/subagents/test_orchestrator_broadcast.py`

**Interfaces:**
- Consumes: `run_bids` (Task 4), `ResponseStore`/`BidStore` (Task 2), `Request`/`Bid` (Task 1), existing `Task`/`TaskStore`, `SubagentTaskPayload`, `publish_board_event` (Task 8 — import lazily; if the module is absent at this point, add a temporary no-op — but implement Task 8 before running e2e).
- Produces:
  - constructor gains `helper_profiles: list[tuple[str, str]]` and `verify_llm: Callable | None`.
  - `async start_async(prompt: str, max_helpers: int) -> str` (was `tasks: list[dict]`).
  - `def start(self, prompt: str, max_helpers: int) -> str`.
  - `async collect_async(job_id) -> {status, responses: list[dict], bids: list[dict], digest}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/subagents/test_orchestrator_broadcast.py
import pytest

from atria.core.subagents.orchestrator import SubagentOrchestrator


class FakeRedis:
    def __init__(self):
        self.h = {}
        self.published = []
    async def hset(self, key, mapping=None):
        self.h.setdefault(key, {}).update(mapping or {})
    async def hget(self, key, field):
        v = self.h.get(key, {}).get(field)
        return v.encode() if isinstance(v, str) else v
    async def hgetall(self, key):
        return {k.encode(): v.encode() for k, v in self.h.get(key, {}).items()}
    async def expire(self, key, ttl):
        return True
    async def set(self, key, val, nx=False, ex=None):
        return True
    async def publish(self, channel, payload):
        self.published.append((channel, payload))


class FakeJobStore:
    def __init__(self):
        self.saved = {}
    async def save(self, job_id, record, ttl):
        self.saved[job_id] = record
    async def load(self, job_id):
        return self.saved.get(job_id)


class Cfg:
    pjob_ttl = 60


def _orch(profiles, verify_llm, enqueued):
    async def enqueue(payload):
        enqueued.append(payload)
        return "kick_" + (payload.subagent_task_id or "?")

    async def await_worker(ids):
        return ids[0], {"status": "done"}

    return SubagentOrchestrator(
        job_store=FakeJobStore(), redis_client=FakeRedis(), config=Cfg(),
        run_async=lambda coro: coro, enqueue_worker=enqueue, await_worker=await_worker,
        owner_id="o", session_id="s", helper_profiles=profiles, verify_llm=verify_llm,
    )


@pytest.mark.asyncio
async def test_only_volunteers_are_enqueued():
    def llm(system, user):
        return "YES 0.9 relevant" if "maps code" in user else "NO 0.0 no"

    enqueued = []
    orch = _orch([("Planner", "maps code"), ("Web-Generator", "builds UIs")], llm, enqueued)
    job_id = await orch.start_async("find the parser", max_helpers=3)
    # Exactly one volunteer (Planner) enqueued; its payload carries no caller-chosen type.
    assert len(enqueued) == 1
    assert enqueued[0].subagent_type == "Planner"
    assert enqueued[0].bid_confidence == 0.9


@pytest.mark.asyncio
async def test_zero_volunteers_marks_done():
    def llm(system, user):
        return "NO 0.0 unrelated"

    enqueued = []
    orch = _orch([("Planner", "maps code")], llm, enqueued)
    job_id = await orch.start_async("x", max_helpers=3)
    assert enqueued == []
    rec = await orch._js.load(job_id)
    assert rec["status"] == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/core/subagents/test_orchestrator_broadcast.py -v`
Expected: FAIL (`start_async` signature mismatch / missing `helper_profiles` kwarg).

- [ ] **Step 3: Replace the orchestrator implementation**

Replace the body of `atria/core/subagents/orchestrator.py` with:

```python
"""Broadcast-request orchestrator (paper arXiv:2510.01285): write an un-addressed
request, run an autonomous per-helper bid, enqueue the existing worker path for
volunteers only, and collect responses (β_r) + the bid roster + note digest."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Awaitable, Callable

from atria.core.blackboard.models import Bid, Request, Task
from atria.core.blackboard.render import render_digest
from atria.core.blackboard.response_store import BidStore, ResponseStore
from atria.core.blackboard.store import BlackboardStore
from atria.core.blackboard.task_store import TaskStore
from atria.core.orchestration.job_store import JobStore
from atria.core.subagents.bid import run_bids
from atria.core.tasks.payload import SubagentTaskPayload

logger = logging.getLogger(__name__)


class SubagentOrchestrator:
    """Run one broadcast request: request → bid → enqueue volunteers → collect."""

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
        helper_profiles: list[tuple[str, str]] | None = None,
        verify_llm: Callable[[str, str], str] | None = None,
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
        self._profiles = helper_profiles or []
        self._verify_llm = verify_llm

    def _emit(self, stage: str, data: dict) -> None:
        if self._cb is None:
            return
        try:
            self._cb(stage, data)
        except Exception as exc:  # noqa: BLE001 — telemetry never breaks the job
            logger.warning("subagent progress_cb failed at %s: %s", stage, exc)

    async def _publish(self, run_id: str, kind: str, payload: dict) -> None:
        try:
            from atria.core.blackboard.board_events import publish_board_event

            await publish_board_event(self._redis, run_id, kind, payload)
        except Exception as exc:  # noqa: BLE001 — viewer events never break the job
            logger.warning("board event publish failed (%s): %s", kind, exc)

    def start(self, prompt: str, max_helpers: int = 3) -> str:
        return self._run_async(self.start_async(prompt, max_helpers))

    def collect(self, job_id: str, block: bool = True, timeout_ms: int = 30000) -> dict:
        return self._run_async(self.collect_async(job_id))

    async def start_async(self, prompt: str, max_helpers: int = 3) -> str:
        """Post a request, bid it out, enqueue volunteers, return the job/request id."""
        job_id = uuid.uuid4().hex[:12]
        bb_id = "sa_" + job_id
        now = time.time()

        request = Request(id=bb_id, prompt=prompt, status="open", ts=now)
        await self._publish(bb_id, "request", request.to_dict())

        bids = await run_bids(bb_id, prompt, self._profiles, self._verify_llm,
                              max_helpers=max_helpers, now=now)
        await BidStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl).add(bids)
        for b in bids:
            await self._publish(bb_id, "bid", b.to_dict())

        volunteers = [b for b in bids if b.volunteered]
        task_objs = [
            Task(id=f"t{i}", subagent_type=b.responder, prompt=prompt, ts=now)
            for i, b in enumerate(volunteers)
        ]
        if task_objs:
            await TaskStore(self._redis, run_id=bb_id, ttl=self._cfg.pjob_ttl).add(task_objs)

        record = {
            "job_id": job_id,
            "bb_id": bb_id,
            "task_ids": [t.id for t in task_objs],
            "status": "running" if task_objs else "done",
        }
        await self._js.save(job_id, record, ttl=self._cfg.pjob_ttl)
        self._emit("started", {
            "job_id": job_id,
            "request": prompt,
            "bids": [b.to_dict() for b in bids],
        })

        if not task_objs:
            self._emit("done", {"job_id": job_id, "status": "done"})
            return job_id

        enqueued: list[str] = []
        for i, (t, b) in enumerate(zip(task_objs, volunteers)):
            payload = SubagentTaskPayload(
                session_id=self._session,
                owner_id=self._owner,
                subagent_type=t.subagent_type,
                prompt=t.prompt,
                working_dir=self._working_dir,
                config_snapshot={},
                blackboard_task_id=bb_id,
                thread_id=i,
                subagent_task_id=t.id,
                bid_confidence=b.confidence,
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
            return {"status": "unknown", "error": f"no such job {job_id}",
                    "responses": [], "bids": [], "digest": ""}
        bb_id = rec["bb_id"]
        ttl = self._cfg.pjob_ttl
        responses = await ResponseStore(self._redis, run_id=bb_id, ttl=ttl).all()
        bids = await BidStore(self._redis, run_id=bb_id, ttl=ttl).all()
        notes = await BlackboardStore(self._redis, task_id=bb_id, ttl=ttl).read_all()
        return {
            "status": rec.get("status", "running"),
            "responses": [r.to_dict() for r in
                          sorted(responses, key=lambda x: -x.confidence)],
            "bids": [b.to_dict() for b in bids],
            "digest": render_digest(notes, viewer_id=0, window_tokens=2000),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/core/subagents/test_orchestrator_broadcast.py -v`
Expected: PASS (2 tests). (The old `tests/.../test_*orchestrator*` for the task-list flow — delete or update in this task if present: `git rm` any test asserting `start_async(tasks=...)`.)

- [ ] **Step 5: Commit**

```bash
git add atria/core/subagents/orchestrator.py tests/core/subagents/test_orchestrator_broadcast.py
git commit -m "feat(subagents): orchestrator request→bid→collect broadcast flow"
```

---

### Task 6: worker writes a Response to the response board

**Files:**
- Modify: `atria/core/tasks/tasks.py:73-97` (write Response alongside status)
- Test: `tests/core/tasks/test_worker_response.py`

**Interfaces:**
- Consumes: `ResponseStore` (Task 2), `Response` (Task 1), `SubagentTaskPayload.bid_confidence` (Task 7 adds the field — do Task 7's payload edit first, or add it here; see note).
- Produces: after a run, one `Response(request_id=blackboard_task_id, responder=subagent_type, content=<result>, confidence=bid_confidence)` in `ResponseStore`.

> Note: `bid_confidence` on the payload is added in Task 7 step 3a. If executing in order, add that one-line field to `payload.py` now so this task can reference it.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/tasks/test_worker_response.py
import pytest

from atria.core.blackboard.response_store import ResponseStore
from atria.core.tasks.tasks import _write_response


class FakeRedis:
    def __init__(self):
        self.h = {}
    async def hset(self, key, mapping=None):
        self.h.setdefault(key, {}).update(mapping or {})
    async def expire(self, key, ttl):
        return True
    async def hgetall(self, key):
        return {k.encode(): v.encode() for k, v in self.h.get(key, {}).items()}


@pytest.mark.asyncio
async def test_write_response_persists_answer():
    r = FakeRedis()
    await _write_response(r, "sa_1", "Planner", "found it at x.py:1", 0.8)
    got = await ResponseStore(r, run_id="sa_1", ttl=60).all()
    assert got[0].content == "found it at x.py:1"
    assert got[0].confidence == 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/core/tasks/test_worker_response.py -v`
Expected: FAIL (`cannot import name '_write_response'`).

- [ ] **Step 3: Add the helper and call it in the worker**

In `atria/core/tasks/tasks.py`, add near `_claim_and_load`:

```python
async def _write_response(
    redis: Any, run_id: str, responder: str, content: str, confidence: float
) -> None:
    """Write one helper answer to the response board β_r (best-effort)."""
    import time

    from atria.core.blackboard.models import Response
    from atria.core.blackboard.response_store import ResponseStore

    store = ResponseStore(redis, run_id=run_id, ttl=3600)
    await store.add([Response(request_id=run_id, responder=responder,
                              content=content[:1000], confidence=confidence, ts=time.time())])
    try:
        from atria.core.blackboard.board_events import publish_board_event

        await publish_board_event(redis, run_id, "response", {
            "request_id": run_id, "responder": responder,
            "content": content[:1000], "confidence": confidence,
        })
    except Exception:  # noqa: BLE001 — viewer event is best-effort
        pass
```

Then, in `run_background_subagent`, in the `if task_store is not None:` block (after `set_status`), add:

```python
        if task_store is not None:
            status = "done" if result.get("success") else "failed"
            await task_store.set_status(
                p.subagent_task_id, status, result=str(result.get("content", ""))[:280]
            )
            if status == "done":
                await _write_response(
                    redis, p.blackboard_task_id, p.subagent_type,
                    str(result.get("content", "")), p.bid_confidence,
                )
```

(Replace the existing `if task_store is not None:` status block with the above — it adds the response write on success.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/core/tasks/test_worker_response.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add atria/core/tasks/tasks.py tests/core/tasks/test_worker_response.py
git commit -m "feat(worker): write helper answers to the response board"
```

---

## Phase 5 — Tool surface

### Task 7: `request_help` / `get_help_responses` tool

**Files:**
- Modify: `atria/core/tasks/payload.py` (add `bid_confidence`)
- Modify: `atria/core/agents/subagents/task_tool.py` (new schema)
- Modify: `atria/core/subagents/tools.py` (builder + handlers)
- Modify: `atria/core/context_engineering/tools/registry.py:204-206` (dispatch keys)
- Modify: `atria/core/context_engineering/tools/registry_mixins/orchestration_ops.py` (handler methods + pass profiles/verify_llm)
- Test: `tests/core/subagents/test_request_help_tool.py`, `tests/core/agents/subagents/test_request_help_schema.py`

**Interfaces:**
- Produces: tool `request_help` with params `{prompt: str, max_helpers?: int}`; `get_help_responses` with `{request_id: str}`. Handlers `execute_request_help(arguments, orch)` and `execute_get_help_responses(arguments, orch)`. `build_subagent_orchestrator(..., helper_profiles=None, verify_llm=None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/agents/subagents/test_request_help_schema.py
from atria.core.agents.subagents.task_tool import (
    REQUEST_HELP_TOOL_NAME, create_request_help_schema,
)


class FakeCfg:
    def __init__(self, name, desc, profile):
        self.name = name
        self.description = desc
        self.capability_profile = profile


class FakeMgr:
    def get_agent_configs(self):
        return [FakeCfg("Planner", "maps code", "explores code"),
                FakeCfg("ask-user", "asks the user", None)]


def test_schema_has_no_subagent_type():
    schema = create_request_help_schema(FakeMgr())
    assert schema["function"]["name"] == REQUEST_HELP_TOOL_NAME == "request_help"
    props = schema["function"]["parameters"]["properties"]
    assert set(props) == {"prompt", "max_helpers"}
    # No caller-chosen routing anywhere in the schema.
    assert "subagent_type" not in str(schema)
```

```python
# tests/core/subagents/test_request_help_tool.py
from atria.core.subagents.tools import execute_get_help_responses, execute_request_help


class FakeOrch:
    def start(self, prompt, max_helpers=3):
        assert prompt == "find the parser"
        return "job123"
    def collect(self, request_id, block=True, timeout_ms=30000):
        return {"status": "done", "responses": [{"responder": "Planner", "content": "x"}],
                "bids": [], "digest": ""}


def test_execute_request_help():
    out = execute_request_help({"prompt": "find the parser"}, FakeOrch())
    assert out["success"] is True
    assert out["request_id"] == "job123"


def test_execute_get_help_responses():
    out = execute_get_help_responses({"request_id": "job123"}, FakeOrch())
    assert out["success"] is True
    assert out["output"]["responses"][0]["responder"] == "Planner"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --no-sync pytest tests/core/subagents/test_request_help_tool.py tests/core/agents/subagents/test_request_help_schema.py -v`
Expected: FAIL (missing names).

- [ ] **Step 3a: Add `bid_confidence` to the payload**

In `atria/core/tasks/payload.py`, add to `SubagentTaskPayload` (after `subagent_task_id`):

```python
    bid_confidence: float = 0.0
```

- [ ] **Step 3b: New tool schema**

In `atria/core/agents/subagents/task_tool.py`, add (keep `format_task_result`):

```python
REQUEST_HELP_TOOL_NAME = "request_help"

REQUEST_HELP_TOOL_DESCRIPTION = """Post an un-addressed request for help on the shared blackboard.

You do NOT choose who answers. Every helper agent independently decides whether it
can contribute, based on its own capabilities. Volunteers run in the background and
write their answers to a response board; you collect them with
`get_help_responses(request_id)`.

## When to Use
- You need information, analysis, or a focused change and are not sure which helper
  is best suited — describe WHAT you need and let helpers self-select.

## Available Helpers (they decide, not you)
{subagent_descriptions}

## Usage Notes
1. Put everything a helper needs in `prompt` — helpers cannot see the conversation.
2. `max_helpers` caps how many volunteers run (default 3).
3. Returns a `request_id`; poll with `get_help_responses(request_id)`.
4. Requires Redis and a running `atria-worker`. If no helper volunteers, you get an
   empty response set — plan, run code yourself, or re-request differently."""


def create_request_help_schema(manager: "SubAgentManager") -> dict[str, Any]:
    """Create the `request_help` tool schema (no caller-chosen routing)."""
    agent_configs = manager.get_agent_configs()
    lines = []
    for c in agent_configs:
        profile = getattr(c, "capability_profile", None)
        if not profile:
            continue  # builtins like ask-user are not volunteers
        lines.append(f"- **{c.name}**: {profile}")
    subagent_descriptions = "\n".join(lines) or "- (no helpers with profiles registered)"
    return {
        "type": "function",
        "function": {
            "name": REQUEST_HELP_TOOL_NAME,
            "description": REQUEST_HELP_TOOL_DESCRIPTION.format(
                subagent_descriptions=subagent_descriptions
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Full self-contained description of what you need. Helpers "
                            "cannot see the conversation."
                        ),
                    },
                    "max_helpers": {
                        "type": "integer",
                        "description": "Max volunteers to run (default 3).",
                    },
                },
                "required": ["prompt"],
            },
        },
    }
```

- [ ] **Step 3c: Builder + handlers in `tools.py`**

In `atria/core/subagents/tools.py`, add `helper_profiles` + `verify_llm` params to `build_subagent_orchestrator` and pass them into `SubagentOrchestrator(...)`:

```python
def build_subagent_orchestrator(
    task_client: Any,
    config: Any,
    owner_id: str,
    session_id: str,
    working_dir: str = "",
    progress_cb: Any = None,
    redis_client: Any = None,
    helper_profiles: list[tuple[str, str]] | None = None,
) -> SubagentOrchestrator:
    ...  # unchanged body up to the return
    from atria.core.blackboard.verify_llm import build_verify_llm
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
        helper_profiles=helper_profiles or [],
        verify_llm=build_verify_llm(config),
    )
```

Replace `execute_subagent_fanout` / `execute_get_subagent_output` with:

```python
def execute_request_help(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Post an un-addressed help request; return a request handle."""
    prompt = arguments.get("prompt")
    if not prompt or not isinstance(prompt, str):
        return {"success": False, "error": "prompt (string) is required", "output": None}
    max_helpers = int(arguments.get("max_helpers", 3) or 3)
    try:
        request_id = orchestrator.start(prompt, max_helpers=max_helpers)
    except Exception as exc:  # noqa: BLE001
        logger.warning("request_help start failed: %s", exc)
        return {"success": False, "error": f"request_help failed: {exc}", "output": None}
    return {
        "success": True,
        "request_id": request_id,
        "status": "running",
        "output": (
            f"[REQUEST POSTED] request_id={request_id}. Helpers are bidding; use "
            "get_help_responses(request_id) to collect volunteers' answers."
        ),
    }


def execute_get_help_responses(arguments: dict, orchestrator: SubagentOrchestrator) -> dict:
    """Collect response-board answers + bid roster + note digest for a request."""
    request_id = arguments.get("request_id", "")
    if not request_id:
        return {"success": False, "error": "request_id is required", "output": None}
    try:
        result = orchestrator.collect(request_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_help_responses failed: %s", exc)
        return {"success": False, "error": f"get_help_responses failed: {exc}", "output": None}
    return {"success": result.get("status") != "unknown", "output": result}
```

- [ ] **Step 3d: Registry dispatch keys**

In `atria/core/context_engineering/tools/registry.py`, replace lines 204-206:

```python
            "request_help": self._execute_request_help,
            "get_help_responses": self._execute_get_help_responses,
```

- [ ] **Step 3e: Handler methods + profiles wiring**

In `atria/core/context_engineering/tools/registry_mixins/orchestration_ops.py`:
- Rename `_execute_subagent_fanout` → `_execute_request_help`, calling `execute_request_help`; rename `_execute_get_subagent_output` → `_execute_get_help_responses`, calling `execute_get_help_responses`.
- In `_get_subagent_orchestrator`, build `helper_profiles` from the manager and pass it:

```python
        mgr = self._subagent_manager
        profiles = []
        if mgr is not None:
            for c in mgr.get_agent_configs():
                p = getattr(c, "capability_profile", None)
                if p:
                    profiles.append((c.name, p))
        ...
        self._subagent_orchestrator = build_subagent_orchestrator(
            task_client=task_client,
            config=self._app_config,
            owner_id=owner_id,
            session_id=session_id,
            working_dir=str(working_dir),
            progress_cb=progress_cb,
            helper_profiles=profiles,
        )
```

- [ ] **Step 3f: Schema registration**

In `atria/core/agents/components/schemas/normal_builder.py:115-126`, change `_build_task_schema` to call `create_request_help_schema` and add a sibling that registers `get_help_responses`. Update the import and any place that referenced `create_task_tool_schema` / the old tool name. Also update the `get_subagent_output`/`get_help_responses` schema (search `normal_builder.py` and `agent_tools.py` for `get_subagent_output` and rename to `get_help_responses` with param `request_id`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/core/subagents/test_request_help_tool.py tests/core/agents/subagents/test_request_help_schema.py -v`
Expected: PASS. Also run `uv run --no-sync pytest tests/core/context_engineering/tools/ -k registry -v` and fix any test still referencing `subagent`/`get_subagent_output`.

- [ ] **Step 5: Commit**

```bash
git add atria/core/tasks/payload.py atria/core/agents/subagents/task_tool.py atria/core/subagents/tools.py atria/core/context_engineering/tools/registry.py atria/core/context_engineering/tools/registry_mixins/orchestration_ops.py atria/core/agents/components/schemas/normal_builder.py tests/core/subagents/test_request_help_tool.py tests/core/agents/subagents/test_request_help_schema.py
git commit -m "feat(tools): request_help/get_help_responses replace subagent routing"
```

---

## Phase 6 — Viewer events → WebSocket

### Task 8: board-event publisher + subscriber bridge

**Files:**
- Create: `atria/core/blackboard/board_events.py`
- Modify: `atria/web/blackboard_subscriber.py:11,44-97`
- Test: `tests/core/blackboard/test_board_events.py`, `tests/web/test_blackboard_subscriber_board.py`

**Interfaces:**
- Produces: `async def publish_board_event(redis, run_id: str, kind: str, payload: dict) -> None` — publishes JSON `{kind, ...payload}` to channel `atria:bb:{run_id}:board`. Subscriber forwards these as WS `{type: "blackboard.{kind}", data: payload}` for `kind in {request, bid, response}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/blackboard/test_board_events.py
import json

import pytest

from atria.core.blackboard.board_events import publish_board_event


class FakeRedis:
    def __init__(self):
        self.published = []
    async def publish(self, channel, payload):
        self.published.append((channel, payload))


@pytest.mark.asyncio
async def test_publish_board_event():
    r = FakeRedis()
    await publish_board_event(r, "sa_1", "bid", {"responder": "Planner", "volunteered": True})
    channel, payload = r.published[0]
    assert channel == "atria:bb:sa_1:board"
    d = json.loads(payload)
    assert d["kind"] == "bid" and d["responder"] == "Planner"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/core/blackboard/test_board_events.py -v`
Expected: FAIL (missing module).

- [ ] **Step 3a: Create the publisher**

```python
# atria/core/blackboard/board_events.py
"""Publish request/bid/response events for the web-ui blackboard viewer.

Distinct from the note channel (``atria:bb:{id}:notes``): board events describe
the request lifecycle (who bid, who volunteered, who answered) rather than
durable findings. Best-effort — publishing never raises to the caller.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_PREFIX = "atria:bb:"


async def publish_board_event(redis: object, run_id: str, kind: str, payload: dict) -> None:
    """Publish ``{kind, **payload}`` JSON to ``atria:bb:{run_id}:board``."""
    channel = f"{_PREFIX}{run_id}:board"
    event = {"kind": kind, **payload}
    try:
        await redis.publish(channel, json.dumps(event))  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 — viewer telemetry is best-effort
        logger.warning("board event publish failed on %s: %s", channel, exc)
```

- [ ] **Step 3b: Broaden the subscriber**

In `atria/web/blackboard_subscriber.py`:
- Add a second pattern constant: `_BOARD_PATTERN = "atria:bb:*:board"`.
- In `run()`, `await pubsub.psubscribe(_PATTERN, _BOARD_PATTERN)`.
- In `_forward`, branch on the source channel. The pub/sub message dict has key `"channel"`; decode it. If it ends with `:board`, read `kind = payload.pop("kind", "event")` and broadcast `{"type": f"blackboard.{kind}", "data": payload}` (apply the same `_admit` throttle keyed on `payload.get("request_id") or payload.get("task_id") or ""`). Otherwise keep the existing `blackboard.note` path.

Concretely, replace the tail of `_forward` with:

```python
        channel = msg.get("channel")
        if isinstance(channel, (bytes, bytearray)):
            channel = channel.decode()
        key = payload.get("request_id") or payload.get("task_id") or ""
        if not self._admit(key):
            return
        if isinstance(channel, str) and channel.endswith(":board"):
            kind = payload.pop("kind", "event")
            await self._broadcaster.broadcast(
                {"type": f"blackboard.{kind}", "data": payload}
            )
            return
        await self._broadcaster.broadcast({"type": "blackboard.note", "data": payload})
```

- [ ] **Step 3c: Subscriber test**

```python
# tests/web/test_blackboard_subscriber_board.py
import json

import pytest

from atria.web.blackboard_subscriber import BlackboardSubscriber


class FakeBroadcaster:
    def __init__(self):
        self.sent = []
    async def broadcast(self, msg):
        self.sent.append(msg)


@pytest.mark.asyncio
async def test_board_bid_event_forwarded():
    b = FakeBroadcaster()
    sub = BlackboardSubscriber(redis=None, broadcaster=b)
    await sub._forward({
        "channel": b"atria:bb:sa_1:board",
        "data": json.dumps({"kind": "bid", "request_id": "sa_1", "responder": "Planner"}),
    })
    assert b.sent[0]["type"] == "blackboard.bid"
    assert b.sent[0]["data"]["responder"] == "Planner"
```

(Match the real `BlackboardSubscriber.__init__` signature — adjust the constructor call to whatever the current file uses for redis + broadcaster.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --no-sync pytest tests/core/blackboard/test_board_events.py tests/web/test_blackboard_subscriber_board.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add atria/core/blackboard/board_events.py atria/web/blackboard_subscriber.py tests/core/blackboard/test_board_events.py tests/web/test_blackboard_subscriber_board.py
git commit -m "feat(web): publish + bridge blackboard request/bid/response events"
```

---

## Phase 7 — Frontend viewer

### Task 9: `blackboardStore` (Zustand)

**Files:**
- Create: `web-ui/src/stores/blackboardStore.ts`
- Modify: `web-ui/src/App.tsx:6` (side-effect import)
- Modify: `web-ui/src/types/index.ts:215-218` (add WS type literals)
- Test: `web-ui/src/stores/blackboardStore.test.ts` (mirror the existing `solverJobs.test.ts` pattern)

**Interfaces:**
- Produces: `useBlackboardStore` with state `{ requests: Record<string, RequestView>, order: string[], clear() }` where
  `RequestView = { requestId: string; prompt: string; bids: BidView[]; responses: ResponseView[]; status: 'open'|'answered'; startedAt: number }`,
  `BidView = { responder: string; volunteered: boolean; reason: string; confidence: number }`,
  `ResponseView = { responder: string; content: string; confidence: number }`.
  WS handlers: `blackboard.request`, `blackboard.bid`, `blackboard.response`.

- [ ] **Step 1: Write the failing test**

```typescript
// web-ui/src/stores/blackboardStore.test.ts
import { describe, expect, it, beforeEach } from 'vitest';
import { useBlackboardStore, __handleBoardEvent } from './blackboardStore';

describe('blackboardStore', () => {
  beforeEach(() => useBlackboardStore.getState().clear());

  it('adds a request, then bids, then responses', () => {
    __handleBoardEvent('blackboard.request', { id: 'sa_1', prompt: 'find parser', ts: 1 });
    __handleBoardEvent('blackboard.bid',
      { request_id: 'sa_1', responder: 'Planner', volunteered: true, reason: 'ok', confidence: 0.9 });
    __handleBoardEvent('blackboard.bid',
      { request_id: 'sa_1', responder: 'Web-Generator', volunteered: false, reason: 'n/a', confidence: 0 });
    __handleBoardEvent('blackboard.response',
      { request_id: 'sa_1', responder: 'Planner', content: 'parser.py:1', confidence: 0.9 });

    const req = useBlackboardStore.getState().requests['sa_1'];
    expect(req.prompt).toBe('find parser');
    expect(req.bids.length).toBe(2);
    expect(req.bids.filter((b) => b.volunteered).length).toBe(1);
    expect(req.responses[0].content).toBe('parser.py:1');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web-ui && npx vitest run src/stores/blackboardStore.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the store**

```typescript
// web-ui/src/stores/blackboardStore.ts
import { create } from 'zustand';
import { wsClient } from '../api/websocket';

export interface BidView {
  responder: string;
  volunteered: boolean;
  reason: string;
  confidence: number;
}
export interface ResponseView {
  responder: string;
  content: string;
  confidence: number;
}
export interface RequestView {
  requestId: string;
  prompt: string;
  bids: BidView[];
  responses: ResponseView[];
  status: 'open' | 'answered';
  startedAt: number;
}

interface BlackboardState {
  requests: Record<string, RequestView>;
  order: string[];
  clear(): void;
}

export const useBlackboardStore = create<BlackboardState>((set) => ({
  requests: {},
  order: [],
  clear: () => set({ requests: {}, order: [] }),
}));

function upsert(id: string, mut: (r: RequestView) => RequestView) {
  useBlackboardStore.setState((s) => {
    const existing = s.requests[id];
    const base: RequestView = existing ?? {
      requestId: id, prompt: '', bids: [], responses: [], status: 'open', startedAt: Date.now(),
    };
    return {
      requests: { ...s.requests, [id]: mut(base) },
      order: existing ? s.order : [id, ...s.order],
    };
  });
}

// Exported for unit tests; also wired to wsClient below.
export function __handleBoardEvent(type: string, data: any) {
  if (type === 'blackboard.request') {
    upsert(data.id, (r) => ({ ...r, prompt: data.prompt ?? r.prompt }));
  } else if (type === 'blackboard.bid') {
    upsert(data.request_id, (r) => ({
      ...r,
      bids: [...r.bids.filter((b) => b.responder !== data.responder), {
        responder: data.responder, volunteered: !!data.volunteered,
        reason: data.reason ?? '', confidence: Number(data.confidence ?? 0),
      }],
    }));
  } else if (type === 'blackboard.response') {
    upsert(data.request_id, (r) => ({
      ...r,
      status: 'answered',
      responses: [...r.responses.filter((x) => x.responder !== data.responder), {
        responder: data.responder, content: data.content ?? '',
        confidence: Number(data.confidence ?? 0),
      }],
    }));
  }
}

export function initBlackboardStore() {
  wsClient.on('blackboard.request', (m) => __handleBoardEvent('blackboard.request', m.data));
  wsClient.on('blackboard.bid', (m) => __handleBoardEvent('blackboard.bid', m.data));
  wsClient.on('blackboard.response', (m) => __handleBoardEvent('blackboard.response', m.data));
}

initBlackboardStore();
```

Add to `web-ui/src/App.tsx` (next to the existing `import './stores/solverJobs';` at line 6):

```typescript
import './stores/blackboardStore';
```

In `web-ui/src/types/index.ts`, extend the `WSMessage['type']` union with `'blackboard.request' | 'blackboard.bid' | 'blackboard.response'`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web-ui && npx vitest run src/stores/blackboardStore.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web-ui/src/stores/blackboardStore.ts web-ui/src/stores/blackboardStore.test.ts web-ui/src/App.tsx web-ui/src/types/index.ts
git commit -m "feat(web-ui): blackboardStore for request/bid/response events"
```

---

### Task 10: `BlackboardPage` + route

**Files:**
- Create: `web-ui/src/pages/BlackboardPage.tsx`
- Modify: `web-ui/src/App.tsx:54-75` (add route), and nav in `web-ui/src/components/Layout/AppShell.tsx`

**Interfaces:**
- Consumes: `useBlackboardStore` (Task 9).
- Produces: a `/blackboard` page rendering, per request: prompt, a bid roster (volunteer ✓ / decline ✗ + reason + confidence), and the response cards.

- [ ] **Step 1: Create the page** (no separate unit test — verified via build + e2e in Task 11)

```tsx
// web-ui/src/pages/BlackboardPage.tsx
import { useBlackboardStore } from '../stores/blackboardStore';

export function BlackboardPage() {
  const requests = useBlackboardStore((s) => s.requests);
  const order = useBlackboardStore((s) => s.order);
  const clear = useBlackboardStore((s) => s.clear);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto bg-canvas">
      <main>
        <div className="max-w-content mx-auto px-6 py-8">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-xl font-semibold">Blackboard</h1>
            {order.length > 0 && (
              <button className="text-sm text-text-secondary hover:text-text" onClick={clear}>
                Clear
              </button>
            )}
          </div>
          {order.length === 0 && (
            <p className="text-text-secondary text-sm">
              No requests yet. When the agent posts a help request, helpers bid here.
            </p>
          )}
          <div className="space-y-4">
            {order.map((id) => {
              const r = requests[id];
              if (!r) return null;
              return (
                <div key={id} className="rounded-lg border border-border p-4">
                  <div className="flex items-center justify-between">
                    <div className="font-mono text-sm">{r.prompt}</div>
                    <span className="text-xs text-text-secondary">{r.status}</span>
                  </div>
                  <div className="mt-3">
                    <div className="text-xs uppercase text-text-secondary mb-1">Bids</div>
                    <ul className="space-y-1">
                      {r.bids.map((b) => (
                        <li key={b.responder} className="text-sm flex items-center gap-2">
                          <span className={b.volunteered ? 'text-semantic-success' : 'text-text-secondary'}>
                            {b.volunteered ? '✓' : '✗'}
                          </span>
                          <span className="font-medium">{b.responder}</span>
                          <span className="text-text-secondary">
                            ({b.confidence.toFixed(2)}) {b.reason}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  {r.responses.length > 0 && (
                    <div className="mt-3">
                      <div className="text-xs uppercase text-text-secondary mb-1">Responses</div>
                      <ul className="space-y-2">
                        {r.responses.map((resp) => (
                          <li key={resp.responder} className="text-sm">
                            <span className="font-medium">{resp.responder}:</span>{' '}
                            <span className="text-text-secondary">{resp.content}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Add the route + nav**

In `web-ui/src/App.tsx`, inside the `AppShell`-wrapped routes (next to `<Route path="/dispatch" .../>`):

```tsx
        <Route path="/blackboard" element={<BlackboardPage />} />
```

Import it at the top: `import { BlackboardPage } from './pages/BlackboardPage';`. Add a nav entry in `AppShell.tsx` alongside the existing Chat/Dispatch links (match that file's link pattern — `to="/blackboard"`, label "Blackboard").

- [ ] **Step 3: Build to verify it compiles**

Run: `cd web-ui && npm run build`
Expected: `tsc` passes, `vite build` writes to `../atria/web/static`.

- [ ] **Step 4: Commit**

```bash
git add web-ui/src/pages/BlackboardPage.tsx web-ui/src/App.tsx web-ui/src/components/Layout/AppShell.tsx atria/web/static
git commit -m "feat(web-ui): BlackboardPage viewer + route"
```

---

## Phase 8 — Integration & verification

### Task 11: Full unit suite + real end-to-end

**Files:** none (verification only).

- [ ] **Step 1: Run the full new-code unit suite**

Run:
```bash
uv run --no-sync pytest tests/core/blackboard tests/core/subagents tests/core/tasks/test_worker_response.py tests/web/test_blackboard_subscriber_board.py -v
```
Expected: all PASS. Then `cd web-ui && npx vitest run` — frontend stores pass.

- [ ] **Step 2: Confirm no residual master-slave routing**

Run:
```bash
grep -rn "subagent_type" atria/core/agents/subagents/task_tool.py atria/core/subagents/tools.py
grep -rn "\"subagent\"\|get_subagent_output" atria/core/context_engineering/tools/registry.py
```
Expected: the tool schema exposes no `subagent_type`; registry dispatches `request_help`/`get_help_responses`. (Internal `Task.subagent_type` set by the bid is fine.)

- [ ] **Step 3: Real end-to-end (per CLAUDE.md)**

Load the proxy creds from repo `.env` (`OPENAI_API_KEY`, `ATRIA_API_BASE_URL`, model `hosted_vllm/Qwen/Qwen3.5-35B-A3B-FP8`), start redis + `atria-worker`, launch the web UI, and drive a real request:

```bash
# terminal 1
redis-server
# terminal 2
atria-worker            # or the documented worker launch command
# terminal 3
atria run ui
```

In the running agent, trigger a `request_help("Find where the blackboard note store publishes to redis and summarize the channel name")`. Verify against live behavior:
- Bids appear in the Blackboard viewer (Planner volunteers; Web-Generator declines with a reason).
- The volunteer runs and a response appears on the response board / viewer.
- `get_help_responses(request_id)` returns the response + bid roster + note digest.
- With `max_helpers=1`, only one volunteer runs even if two would qualify.
- Kill redis mid-run once to confirm fail-soft (no agent-loop crash; empty responses).

- [ ] **Step 4: Commit any calibration fixes**

```bash
git add -A
git commit -m "test: real e2e calibration for broadcast blackboard"
```

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch to decide merge/PR. Do not push or open a PR unless the user asks.

---

## Self-Review

**Spec coverage:**
- Data model (Request/Response separate board) → Tasks 1, 2, 6. ✓
- Capability profiles → Task 3. ✓
- Broadcast + independent per-helper bid, fail-closed, capped → Tasks 4, 5. ✓
- Fan out to volunteers only, existing worker path → Task 5. ✓
- Tool surface rename (`request_help`/`get_help_responses`, no `subagent_type`) → Task 7. ✓
- Response board separate from notes → Tasks 2, 6. ✓
- Viewer (request + bid roster + responses + notes) + WS events → Tasks 8, 9, 10. ✓
- Removed master-slave routing → Task 7 + verified Task 11 step 2. ✓
- Error handling (fail-open blackboard, fail-closed bids, zero-volunteer path) → Tasks 4, 5, 8. ✓
- Testing (unit + real e2e) → every task + Task 11. ✓
- Out of scope (clustering, dynamic profiles, response admission) → not planned. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. The one soft spot is Task 7 step 3f and Task 8 step 3b/3c, which describe edits against files whose exact current lines the implementer must open (`normal_builder.py`, the `BlackboardSubscriber.__init__` signature) — instructions name the exact function and change, and give the replacement code, so no guesswork remains beyond matching the local signature.

**Type consistency:** `Request.id` == the orchestrator `bb_id` == `request_id` used by `ResponseStore`/`BidStore`/board events == the frontend `data.id` (request event) / `data.request_id` (bid/response events) — consistent. `bid_confidence` flows payload → `_write_response` → `Response.confidence`. Tool returns `request_id` (== `job_id`) consumed by `get_help_responses(request_id)`. Store keys `atria:bb:{run_id}:{responses,bids,board,notes,tasks}` share the `sa_{job_id}` run id.
