# Produce Track B — Minder SDK Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Layer the Minder co-work surface (Read / Event / Command / Guidance, MVP subset) onto the finished Produce Track A additively, using `minder_python_sdk` (backend) + `minder_ui_sdk` (frontend), without changing Track A logic or behavior.

**Architecture:** A new `backend/events.py` seam (no-op by default) that Track A services call after each relevant write. A new `backend/agent/` package (Connector + reads/events/commands/guidance) that only reads/calls Track A services in-process. `app.py` branches: when `PR_AGENT_ENABLED`, the top-level ASGI becomes `conn.asgi()` (so the connector lifespan runs announce/heartbeat) with Track A routers + SPA attached; otherwise it is today's plain Track A app. Frontend gates the agent surface behind `agentEnabled`.

**Tech Stack:** FastAPI + SQLAlchemy (Track A, done); `minder_python_sdk` Connector (`@conn.read`, `@conn.tool` with risk gate, `@conn.event`/`emit_event`, `conn.context.*`, `decision_packet`, `assumption`, `conn.asgi`, `conn.invoke`); React + `minder_ui_sdk` (`AgentDriverProvider`, `AgentRegistryProvider`, `Agent.*`, `DecisionPacket`, `useModuleEvents`).

## Global Constraints

- **Additive only:** never change Track A business logic or human-facing behavior. Track A services gain exactly one `events.emit(...)` line per relevant write. `agent/` is new; Track A never imports it. With `PR_AGENT_ENABLED=0`, produce runs byte-identically to today (no connector, seam no-op).
- **Scope = MVP co-work subset:** Read R01–R07; Event E01/E02/E03/E05; Guidance G01+G03; Command C03/C07/C09 (all `risk="low"`). No C05/C08, no G02/G04/G05/G06, no E04/E06/E07.
- **Naming:** module id `produce`; env `PR_*`; `PR_AGENT_ENABLED` (default `0`).
- **SDK signatures (verbatim):** `conn.read(name, *, description="", params_model=None, when_to_use="", examples=None)`; `conn.tool(name, *, description="", params_model=None, card_type=None, risk="low", reversible=None, undo=None, when_to_use="", examples=None)`; `conn.event(event_type, *, description="", schema=None)`; `conn.on_event(fn)`; `conn.emit_event(event_type, payload=None, *, source="module", actor=None, session_id=None)`; `conn.invoke(tool_name, arguments, *, principal=None, session_id=None, autonomy=None)`; `conn.asgi(*, cors_origins=None) -> FastAPI`; `conn.on_startup(fn)`; `conn.context.state(name, description)(fn)` / `conn.context.knowledge(text)` / `conn.context.note(name, text)`; from `minder_python_sdk`: `decision_packet(...)`, `assumption(text, confidence=None)`, `card(...)`, `MinderClient`.
- **Tests:** `uv run --no-sync pytest` from `modules/produce/backend/`. Agent tests need the SDK installed — guard each agent test module with `pytest.importorskip("minder_python_sdk")`. Reuse the SQLite-monkeypatch fixture. `tests/` is gitignored — `git add -f`.
- **Commits:** Conventional Commits; NO `Co-Authored-By: Claude`.

## File Structure

- `backend/events.py` — CREATE. Seam: `emit(kind, payload)`, `subscribe(fn)`, `_listeners`.
- `backend/domain/wip/service.py` — MODIFY. `emit` in `start_job` / `complete_job`.
- `backend/domain/sop/service.py` — MODIFY. `emit` in `confirm_step`.
- `backend/domain/downtime/service.py` — MODIFY. `emit` in `open_downtime` / `close_downtime` / `raise_andon`.
- `backend/domain/exception/service.py` — MODIFY. `emit` in `raise_exception`.
- `backend/agent/__init__.py` — CREATE (empty).
- `backend/agent/connector.py` — CREATE. `conn = Connector(...)`, sink, imports reads/events/commands/guidance to register them, exposes `build_app()`.
- `backend/agent/reads.py` — CREATE. `@conn.read` R01–R07.
- `backend/agent/events.py` — CREATE. `conn.event(...)` specs + `produce_events.subscribe(_forward)`.
- `backend/agent/commands.py` — CREATE. `@conn.tool` C03/C07/C09.
- `backend/agent/guidance.py` — CREATE. `conn.context.*` + `decision_packet` builders + `@conn.tool` for G01/G03 surfacing.
- `backend/app.py` — MODIFY. Branch on `PR_AGENT_ENABLED`.
- `backend/Dockerfile` — MODIFY. Install `minder_python_sdk`.
- `frontend/src/agent/` + `frontend/src/dashboard.tsx` + `frontend/src/main.tsx` — MODIFY/CREATE. Agent surface gated by `agentEnabled`.
- `docker-compose.yml` — MODIFY. Announce/Keycloak env for `produce-web`.

---

## Phase 1 — Event seam (Track A emits; still standalone)

### Task 1: The seam module

**Files:**
- Create: `modules/produce/backend/events.py`
- Test: `modules/produce/backend/tests/test_events_seam.py`

**Interfaces:**
- Produces: `emit(kind: str, payload: dict) -> None`; `subscribe(fn: Callable[[str, dict], None]) -> None`; `unsubscribe(fn) -> None`; `clear() -> None` (test helper).

- [ ] **Step 1: Write the failing test** — `tests/test_events_seam.py`:

```python
"""Event seam: emit reaches subscribers; no subscriber = harmless no-op."""

from __future__ import annotations

import events


def teardown_function():
    events.clear()


def test_emit_reaches_subscriber():
    seen = []
    events.subscribe(lambda kind, payload: seen.append((kind, payload)))
    events.emit("downtime.opened", {"id": 1})
    assert seen == [("downtime.opened", {"id": 1})]


def test_emit_no_subscriber_is_noop():
    events.emit("job.started", {"id": 9})  # must not raise


def test_listener_error_does_not_propagate():
    def boom(kind, payload):
        raise RuntimeError("listener bug")

    events.subscribe(boom)
    events.emit("andon.raised", {"id": 2})  # must not raise
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_events_seam.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'events'`).

- [ ] **Step 3: Implement** — `backend/events.py`:

```python
"""Track A -> Track B event seam. Track A services call emit() after a write.
Default no-op (no subscribers) so Track A runs standalone. The connector (Track B)
subscribes to forward envelopes to Minder. Never raises into the caller."""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("produce.events")

_listeners: list[Callable[[str, dict], None]] = []


def subscribe(fn: Callable[[str, dict], None]) -> None:
    if fn not in _listeners:
        _listeners.append(fn)


def unsubscribe(fn: Callable[[str, dict], None]) -> None:
    if fn in _listeners:
        _listeners.remove(fn)


def clear() -> None:
    _listeners.clear()


def emit(kind: str, payload: dict) -> None:
    """Fire-and-forget. A listener error is logged, never propagated to the write."""
    for fn in list(_listeners):
        try:
            fn(kind, payload)
        except Exception as exc:  # noqa: BLE001 — a listener must never break a human write
            logger.warning("event listener failed for %s: %s", kind, exc)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --no-sync pytest tests/test_events_seam.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/events.py
git add -f modules/produce/backend/tests/test_events_seam.py
git commit -m "feat(produce): event seam (emit/subscribe, no-op by default)"
```

### Task 2: Wire E01/E02/E03/E05 emissions into Track A services

**Files:**
- Modify: `modules/produce/backend/domain/wip/service.py`, `domain/sop/service.py`, `domain/downtime/service.py`, `domain/exception/service.py`
- Test: `modules/produce/backend/tests/test_event_emissions.py`

**Interfaces:**
- Consumes: `events.emit` (Task 1).
- Produces: emissions with these exact kinds + payload = the service's returned dict:
  `job.started`, `job.completed`, `step.confirmed`, `downtime.opened`, `downtime.closed`, `andon.raised`, `exception.raised`.

- [ ] **Step 1: Write the failing test** — `tests/test_event_emissions.py`:

```python
"""Track A writes emit the right kinds through the seam (E01/E02/E03/E05)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db
import events


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    seen = []
    events.subscribe(lambda k, p: seen.append((k, p)))
    yield seen
    events.clear()


def _kinds(seen):
    return [k for k, _ in seen]


def test_wip_and_sop_emissions(sqlite_engine):
    from domain.sop import service as sop
    from domain.wip import service as wip

    job = wip.start_job(task_id=1, station_id=1)
    wip.complete_job(job["id"])
    v = sop.add_draft_version(sop.create_sop("S1", "T")["id"], steps=[{"name": "a"}])
    sop.publish_version(v["id"])
    sop.confirm_step(job_id=job["id"], sop_version_id=v["id"], step_index=0)
    assert "job.started" in _kinds(sqlite_engine)
    assert "job.completed" in _kinds(sqlite_engine)
    assert "step.confirmed" in _kinds(sqlite_engine)


def test_downtime_and_exception_emissions(sqlite_engine):
    from domain.downtime import service as dt
    from domain.exception import service as exc

    d = dt.open_downtime(station_id=1, category="Mech")
    dt.close_downtime(d["id"])
    dt.raise_andon(line_id=1, station_id=1)
    exc.raise_exception(line_id=1, reason="máy hỏng")
    kinds = _kinds(sqlite_engine)
    assert {"downtime.opened", "downtime.closed", "andon.raised", "exception.raised"} <= set(kinds)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_event_emissions.py -q`
Expected: FAIL (kinds missing — services don't emit yet).

- [ ] **Step 3: Implement** — add `import events` at the top of each service, and emit right before each `return dict` for the target writes.

In `domain/wip/service.py`, `start_job` — before `return job.as_dict()`:
```python
        result = job.as_dict()
        events.emit("job.started", result)
        return result
```
`complete_job` — before `return job.as_dict()`:
```python
        result = job.as_dict()
        events.emit("job.completed", result)
        return result
```

In `domain/sop/service.py`, `confirm_step` — before `return c.as_dict()`:
```python
        result = c.as_dict()
        events.emit("step.confirmed", result)
        return result
```

In `domain/downtime/service.py`: `open_downtime` emit `"downtime.opened"`, `close_downtime` emit `"downtime.closed"`, `raise_andon` emit `"andon.raised"` — each with the returned dict, same pattern.

In `domain/exception/service.py`, `raise_exception` — emit `"exception.raised"` with the returned dict.

Add `import events` to each of the four service modules (top-level, with the other imports).

- [ ] **Step 4: Run to verify it passes (+ full regression: Track A unaffected)**

Run: `uv run --no-sync pytest -q`
Expected: `test_event_emissions.py` PASS; ALL prior Track A tests still PASS (emissions are no-op there — no subscriber).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/domain/wip/service.py modules/produce/backend/domain/sop/service.py modules/produce/backend/domain/downtime/service.py modules/produce/backend/domain/exception/service.py
git add -f modules/produce/backend/tests/test_event_emissions.py
git commit -m "feat(produce): emit E01/E02/E03/E05 events from Track A writes via seam"
```

---

## Phase 2 — Connector bootstrap + app composition

### Task 3: Connector object + agent package

**Files:**
- Create: `modules/produce/backend/agent/__init__.py` (empty), `modules/produce/backend/agent/connector.py`
- Test: `modules/produce/backend/tests/test_agent_bootstrap.py`

**Interfaces:**
- Produces: `agent.connector.conn` (a `Connector`), `agent.connector.build_app() -> FastAPI`. `conn` has `default_autonomy="medium"`, `min_core_version="2"`, name `"produce"`, and its event sink set to `conn.minder_client().emit_event` (best-effort; skipped if announce config absent).

- [ ] **Step 1: Write the failing test** — `tests/test_agent_bootstrap.py`:

```python
"""Connector bootstraps and exposes a manifest with the produce name."""

from __future__ import annotations

import pytest

pytest.importorskip("minder_python_sdk")


def test_connector_identity():
    from agent.connector import conn

    assert conn.name == "produce"
    assert conn.default_autonomy == "medium"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_agent_bootstrap.py -q`
Expected: SKIP if SDK absent, else FAIL (`ModuleNotFoundError: agent.connector`).

- [ ] **Step 3: Implement** — `backend/agent/__init__.py` empty; `backend/agent/connector.py`:

```python
"""Produce Track B connector. Additive co-work surface over Track A services.
Imported ONLY when PR_AGENT_ENABLED; requires minder_python_sdk."""

from __future__ import annotations

import logging

from minder_python_sdk import Connector

logger = logging.getLogger("produce.agent")

conn = Connector(
    "produce",
    version="1",
    display_name="Produce",
    public_base_env="PR_PUBLIC_BASE",
    min_core_version="2",
    default_autonomy="medium",
)


def _wire_event_sink() -> None:
    """Forward emitted envelopes to Minder's event log (best-effort)."""
    try:
        client = conn.minder_client()
        conn.set_event_sink(client.emit_event)
    except Exception as exc:  # noqa: BLE001 — announce config may be absent in dev
        logger.warning("event sink not wired (announce config absent?): %s", exc)


def build_app():
    """Compose the connector ASGI with Track A routers + SPA attached.

    conn.asgi() owns the lifespan that runs announce/heartbeat, so it must be the
    top-level app (Starlette sub-app mounts do not run lifespans)."""
    import os

    import db
    from domain.config import routes as config_routes
    from domain.work import routes as work_routes
    from domain.sop import routes as sop_routes
    from domain.wip import routes as wip_routes
    from domain.downtime import routes as downtime_routes
    from domain.scrap import routes as scrap_routes
    from domain.oee import routes as oee_routes
    from domain.setup import routes as setup_routes
    from domain.handover import routes as handover_routes
    from domain.exception import routes as exception_routes
    from domain.report import routes as report_routes

    # Register the co-work surface on `conn` (import side effects).
    from agent import reads, events as agent_events, commands, guidance  # noqa: F401

    conn.on_startup(db.init_db)
    conn.on_startup(agent_events.attach)
    _wire_event_sink()

    app = conn.asgi(cors_origins=["*"])
    for mod in (
        config_routes, work_routes, sop_routes, wip_routes, downtime_routes,
        scrap_routes, oee_routes, setup_routes, handover_routes, exception_routes,
        report_routes,
    ):
        app.include_router(mod.router)

    from fastapi.staticfiles import StaticFiles

    dist = os.environ.get("PR_DASHBOARD_DIST", os.path.join(os.path.dirname(__file__), "..", "frontend_dist"))
    if os.path.isdir(dist):
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    return app
```

Note: `agent.events.attach` and the `reads`/`commands`/`guidance` modules are created in later tasks; this task's test only imports `agent.connector` (which does not import them at module load — they are imported inside `build_app`). Verify the test passes without the later modules.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --no-sync pytest tests/test_agent_bootstrap.py -q`
Expected: PASS (or SKIP if SDK absent).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/agent/__init__.py modules/produce/backend/agent/connector.py
git add -f modules/produce/backend/tests/test_agent_bootstrap.py
git commit -m "feat(produce): Track B connector bootstrap (Connector + build_app)"
```

### Task 4: app.py composition branch + PR_AGENT_ENABLED

**Files:**
- Modify: `modules/produce/backend/app.py`
- Test: `modules/produce/backend/tests/test_smoke.py` (extend)

**Interfaces:**
- Produces: `app` = today's Track A FastAPI when `PR_AGENT_ENABLED` is falsy; `agent.connector.build_app()` when truthy.

- [ ] **Step 1: Write the failing test** — append to `tests/test_smoke.py`:

```python
def test_agent_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PR_AGENT_ENABLED", raising=False)
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    # Track A app has /health and NO /connector/manifest route.
    paths = {getattr(r, "path", "") for r in app_mod.app.routes}
    assert "/health" in paths
    assert "/connector/manifest" not in paths
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_smoke.py::test_agent_disabled_by_default -q`
Expected: FAIL until the branch exists (import reload semantics) OR PASS trivially — if it errors, fix in Step 3.

- [ ] **Step 3: Implement** — restructure `app.py` so the module builds `app` via a function guarded by the env. Replace the current app construction with:

```python
import os

_AGENT_ENABLED = os.environ.get("PR_AGENT_ENABLED", "0") not in ("", "0", "false", "False")

if _AGENT_ENABLED:
    from agent.connector import build_app

    app = build_app()
else:
    app = _build_track_a_app()  # the existing FastAPI(...) + routers + /health + static
```

Wrap today's construction (lifespan, `app = FastAPI(...)`, CORS, router loop, `/health`, StaticFiles mount) into a `def _build_track_a_app() -> FastAPI:` that returns `app`. Keep all existing behavior identical inside it.

- [ ] **Step 4: Run to verify it passes (+ regression)**

Run: `uv run --no-sync pytest -q`
Expected: all Track A tests PASS; new smoke test PASS. (`PR_AGENT_ENABLED` unset in dev, so the SDK is never imported.)

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/app.py
git add -f modules/produce/backend/tests/test_smoke.py
git commit -m "feat(produce): app.py branches on PR_AGENT_ENABLED (Track A default)"
```

---

## Phase 3 — Reads (R01–R07)

### Task 5: `@conn.read` R01–R07

**Files:**
- Create: `modules/produce/backend/agent/reads.py`
- Test: `modules/produce/backend/tests/test_agent_reads.py`

**Interfaces:**
- Consumes: `agent.connector.conn`; Track A services.
- Produces: registered reads `read_queue`, `read_wip`, `read_oee`, `read_downtime`, `read_sop`, `read_exceptions`, `read_handover` — each callable via `conn.invoke(name, args)` returning `{"output": ...}`.

- [ ] **Step 1: Write the failing test** — `tests/test_agent_reads.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("minder_python_sdk")

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_read_queue_returns_operator_tasks():
    import agent.reads  # noqa: F401 — registers reads
    from agent.connector import conn
    from domain.work import service as work

    line = 1
    t = work.create_task(line)
    work.claim_task(t["id"], "op1")
    out = conn.invoke("read_queue", {"assignee_id": "op1"})
    assert out["output"] and out["output"][0]["assignee_id"] == "op1"


def test_read_oee_reports_error_without_order():
    import agent.reads  # noqa: F401
    from agent.connector import conn

    out = conn.invoke("read_oee", {"shift_id": 1, "total_count": 0})
    assert "error" in out["output"] or out["output"].get("oee") is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_agent_reads.py -q`
Expected: FAIL (`ModuleNotFoundError: agent.reads`) or SKIP if SDK absent.

- [ ] **Step 3: Implement** — `backend/agent/reads.py`:

```python
"""Track B Read surface (R01-R07). Typed, read-only queries over Track A services."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent.connector import conn
from domain.downtime import service as downtime_service
from domain.exception import service as exception_service
from domain.handover import service as handover_service
from domain.oee import service as oee_service
from domain.sop import service as sop_service
from domain.wip import service as wip_service
from domain.work import service as work_service


class QueueQuery(BaseModel):
    assignee_id: str = Field(description="Operator id whose queue to read.")


@conn.read("read_queue", description="R01 — operator queue by priority.", params_model=QueueQuery,
           when_to_use="To see what an operator should work on next.")
def read_queue(assignee_id: str):
    return {"output": work_service.operator_queue(assignee_id)}


class LineQuery(BaseModel):
    line_id: int


@conn.read("read_wip", description="R02 — WIP per station for a line.", params_model=LineQuery,
           when_to_use="To find bottlenecks / WIP build-up on a line.")
def read_wip(line_id: int):
    return {"output": {"by_station": wip_service.wip_by_station()}}


class ShiftQuery(BaseModel):
    shift_id: int
    total_count: int = 0


@conn.read("read_oee", description="R03 — shift OEE + three losses.", params_model=ShiftQuery,
           when_to_use="To check whether the shift is on plan (OEE vs target).")
def read_oee(shift_id: int, total_count: int = 0):
    try:
        return {"output": oee_service.shift_oee(shift_id, total_count)}
    except oee_service.OeeError as exc:
        return {"output": {"error": str(exc)}}


@conn.read("read_downtime", description="R04 — open downtime + reason library.", params_model=LineQuery,
           when_to_use="To see current stoppages and the valid reason codes.")
def read_downtime(line_id: int):
    return {"output": {"open": downtime_service.open_downtimes(),
                       "reasons": downtime_service.reason_library(line_id)}}


class SopQuery(BaseModel):
    sop_id: int


@conn.read("read_sop", description="R05 — released SOP + steps for an operation.", params_model=SopQuery,
           when_to_use="To read the current approved work instruction.")
def read_sop(sop_id: int):
    return {"output": sop_service.released_version(sop_id)}


@conn.read("read_exceptions", description="R06 — open + escalated exceptions.", params_model=LineQuery,
           when_to_use="To see blocked jobs and what has been escalated.")
def read_exceptions(line_id: int):
    return {"output": {"open": exception_service.open_exceptions(line_id),
                       "escalated": exception_service.escalated_exceptions()}}


class HandoverQuery(BaseModel):
    from_shift_id: int


@conn.read("read_handover", description="R07 — shift handover + carry-forward.", params_model=HandoverQuery,
           when_to_use="To read the outgoing shift's handover before starting.")
def read_handover(from_shift_id: int):
    return {"output": handover_service.read_handover(from_shift_id)}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --no-sync pytest tests/test_agent_reads.py -q`
Expected: PASS (or SKIP if SDK absent).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/agent/reads.py
git add -f modules/produce/backend/tests/test_agent_reads.py
git commit -m "feat(produce): Track B Read surface R01-R07 (@conn.read)"
```

---

## Phase 4 — Events registration

### Task 6: Declare event specs + forward the seam to Minder

**Files:**
- Create: `modules/produce/backend/agent/events.py`
- Test: `modules/produce/backend/tests/test_agent_events.py`

**Interfaces:**
- Consumes: `agent.connector.conn`, `events` (seam).
- Produces: `attach() -> None` (subscribes the seam forwarder; idempotent). Declares `conn.event(...)` for the 7 kinds. When a Track A write emits, `conn.emit_event(kind, payload)` fires (captured by `conn.on_event` subscribers + the sink).

- [ ] **Step 1: Write the failing test** — `tests/test_agent_events.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("minder_python_sdk")

import db
import events as seam


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield
    seam.clear()


def test_seam_forwards_to_connector_envelopes():
    import agent.events as agent_events
    from agent.connector import conn
    from domain.downtime import service as dt

    captured = []
    conn.on_event(lambda env: captured.append(env.type))
    agent_events.attach()

    d = dt.open_downtime(station_id=1, category="Mech")
    dt.close_downtime(d["id"])
    assert "downtime.opened" in captured
    assert "downtime.closed" in captured
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_agent_events.py -q`
Expected: FAIL (`ModuleNotFoundError: agent.events`) or SKIP.

- [ ] **Step 3: Implement** — `backend/agent/events.py`:

```python
"""Track B event registration. Declares the module's event types and forwards the
Track A seam to conn.emit_event (which reaches on_event subscribers + the sink)."""

from __future__ import annotations

import events as seam
from agent.connector import conn

_KINDS = [
    ("job.started", "E01 — a job started"),
    ("job.completed", "E01 — a job completed"),
    ("step.confirmed", "E01 — an SOP step was confirmed"),
    ("downtime.opened", "E02 — a downtime event opened"),
    ("downtime.closed", "E02 — a downtime event closed"),
    ("andon.raised", "E03 — an operator called andon"),
    ("exception.raised", "E05 — a job was blocked (exception raised)"),
]

for _type, _desc in _KINDS:
    conn.event(_type, description=_desc)


def _forward(kind: str, payload: dict) -> None:
    conn.emit_event(kind, payload, source="module")


_attached = False


def attach() -> None:
    """Subscribe the seam forwarder exactly once."""
    global _attached
    if not _attached:
        seam.subscribe(_forward)
        _attached = True
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --no-sync pytest tests/test_agent_events.py -q`
Expected: PASS (or SKIP).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/agent/events.py
git add -f modules/produce/backend/tests/test_agent_events.py
git commit -m "feat(produce): Track B event specs + seam->conn.emit_event forwarder"
```

---

## Phase 5 — Commands (C03/C07/C09)

### Task 7: `@conn.tool` C03/C07/C09 with gate + reversibility

**Files:**
- Create: `modules/produce/backend/agent/commands.py`
- Test: `modules/produce/backend/tests/test_agent_commands.py`

**Interfaces:**
- Consumes: `conn`, Track A services, `report_service.end_of_shift_report`.
- Produces: tools `cmd_raise_exception` (C03), `cmd_draft_handover` (C07), `cmd_update_production` (C09) — each `risk="low"`, `reversible=True`, with an `undo` note; callable via `conn.invoke`.

- [ ] **Step 1: Write the failing test** — `tests/test_agent_commands.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("minder_python_sdk")

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_c03_creates_and_escalates_exception():
    import agent.commands  # noqa: F401
    from agent.connector import conn
    from domain.exception import service as exc

    out = conn.invoke("cmd_raise_exception", {"line_id": 1, "reason": "thiếu vật tư"})
    assert out.get("output", {}).get("status") == "escalated"
    assert len(exc.escalated_exceptions()) == 1


def test_c09_updates_production_count():
    import agent.commands  # noqa: F401
    from agent.connector import conn
    from domain.wip import service as wip

    conn.invoke("cmd_update_production", {"station_id": 3, "qty": 10})
    assert wip.station_total(3) == 10
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_agent_commands.py -q`
Expected: FAIL (`ModuleNotFoundError: agent.commands`) or SKIP.

- [ ] **Step 3: Implement** — `backend/agent/commands.py`:

```python
"""Track B Command surface (C03/C07/C09). Low-risk, reversible, gated writes over
Track A services. Each carries an assumption ledger + an undo note."""

from __future__ import annotations

from pydantic import BaseModel, Field

from minder_python_sdk import assumption, card

from agent.connector import conn
from domain.exception import service as exception_service
from domain.handover import service as handover_service
from domain.report import service as report_service
from domain.wip import service as wip_service


class RaiseExceptionArgs(BaseModel):
    line_id: int
    reason: str = Field(description="Why the job is blocked (missing material, machine down, QC wait).")
    task_id: int | None = None
    job_id: int | None = None


@conn.tool(
    "cmd_raise_exception",
    description="C03 — create an exception from a detected block and escalate to the supervisor.",
    params_model=RaiseExceptionArgs,
    risk="low",
    reversible=True,
    undo="Resolve the exception via exception.resolve(id).",
    when_to_use="When an event indicates a blocked job that a supervisor should see.",
)
def cmd_raise_exception(line_id: int, reason: str, task_id: int | None = None, job_id: int | None = None):
    exc = exception_service.raise_exception(line_id, reason, task_id=task_id, job_id=job_id, raised_by="minder")
    escalated = exception_service.escalate(exc["id"])
    return {
        "output": escalated,
        "card": card(f"Raised + escalated exception {escalated['id']}.", confidence=0.9),
        "assumptions": [assumption("The detected block is real and needs supervisor attention.", 0.8)],
    }


class DraftHandoverArgs(BaseModel):
    line_id: int
    from_shift_id: int
    total_count: int = 0


@conn.tool(
    "cmd_draft_handover",
    description="C07 — build an auto-summarized end-of-shift handover draft.",
    params_model=DraftHandoverArgs,
    risk="low",
    reversible=True,
    undo="Delete the draft handover row.",
    when_to_use="At shift end, to pre-fill the handover from live data.",
)
def cmd_draft_handover(line_id: int, from_shift_id: int, total_count: int = 0):
    report = report_service.end_of_shift_report(line_id, from_shift_id, total_count)
    h = handover_service.create_handover(
        line_id, from_shift_id, output_count=report["output_count"],
        notes=f"Auto-draft: scrap={report['scrap_count']}, oee={report['oee']}",
    )
    return {
        "output": h,
        "card": card(f"Drafted handover {h['id']} for shift {from_shift_id}.", confidence=0.85),
        "assumptions": [assumption("Live counts are complete enough to summarize the shift.", 0.7)],
    }


class UpdateProductionArgs(BaseModel):
    station_id: int
    qty: int | None = None
    status: str | None = None
    job_id: int | None = None


@conn.tool(
    "cmd_update_production",
    description="C09 — update a production record (count and/or station status).",
    params_model=UpdateProductionArgs,
    risk="low",
    reversible=True,
    undo="Record the inverse count / restore the prior station status.",
    when_to_use="To reconcile a production record from a trusted signal.",
)
def cmd_update_production(station_id: int, qty: int | None = None, status: str | None = None, job_id: int | None = None):
    out = {}
    if qty is not None:
        out["count"] = wip_service.record_count(station_id, qty, job_id)
    if status is not None:
        out["status"] = wip_service.set_station_status(station_id, status)
    return {
        "output": out,
        "card": card(f"Updated production record for station {station_id}.", confidence=0.8),
        "assumptions": [assumption("The source signal for this update is trustworthy.", 0.7)],
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --no-sync pytest tests/test_agent_commands.py -q`
Expected: PASS (or SKIP).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/agent/commands.py
git add -f modules/produce/backend/tests/test_agent_commands.py
git commit -m "feat(produce): Track B Command surface C03/C07/C09 (gated, reversible)"
```

---

## Phase 6 — Guidance backend

### Task 8: `conn.context.*` + decision-packet guidance tools (G01/G03)

**Files:**
- Create: `modules/produce/backend/agent/guidance.py`
- Test: `modules/produce/backend/tests/test_agent_guidance.py`

**Interfaces:**
- Consumes: `conn`, Track A services.
- Produces: `conn.context.state("shift_oee")` + `state("open_exceptions")`; `conn.context.knowledge(...)` guardrails; `conn.context.note(...)` per persona area; tool `guide_next_step` (G01) returning a suggestion card; tool `guide_decision_packet` (G03) returning a `decision_packet` for supervisor approval.

- [ ] **Step 1: Write the failing test** — `tests/test_agent_guidance.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pytest.importorskip("minder_python_sdk")

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_guide_next_step_returns_card():
    import agent.guidance  # noqa: F401
    from agent.connector import conn

    sop = _publish_sop()
    out = conn.invoke("guide_next_step", {"job_id": 1, "sop_id": sop})
    assert out["output"]  # a suggestion string/dict


def test_guide_decision_packet_has_assumptions():
    import agent.guidance  # noqa: F401
    from agent.connector import conn

    out = conn.invoke("guide_decision_packet", {"line_id": 1, "reason": "máy hỏng"})
    packet = out["output"]
    assert packet["kind"] == "decision" or "assumptions" in packet


def _publish_sop():
    from domain.sop import service as sop
    s = sop.create_sop("S1", "T")["id"]
    v = sop.add_draft_version(s, steps=[{"name": "torque", "required": True}])
    sop.publish_version(v["id"])
    return s
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync pytest tests/test_agent_guidance.py -q`
Expected: FAIL (`ModuleNotFoundError: agent.guidance`) or SKIP.

- [ ] **Step 3: Implement** — `backend/agent/guidance.py`:

```python
"""Track B Guidance surface (G01/G03). Declarative context + suggestion / decision
packets rendered into the UI; the person decides."""

from __future__ import annotations

from pydantic import BaseModel

from minder_python_sdk import assumption, card, decision_packet

from agent.connector import conn
from domain.exception import service as exception_service
from domain.oee import service as oee_service
from domain.sop import service as sop_service

conn.context.knowledge(
    "Produce is an MES. A licensed operator/supervisor stays in the loop for every "
    "dispatch decision. Never bypass poka-yoke or the risk gate."
)
conn.context.note("operator", "Operator screen: queue, e-SOP execution, WIP, downtime, scrap.")
conn.context.note("supervisor", "Supervisor screen: shift OEE, escalations, handover, holds.")


@conn.context.state("open_exceptions", "Currently open exceptions across lines 1-3.")
def _state_exceptions():
    out = []
    for line_id in (1, 2, 3):
        out.extend(exception_service.open_exceptions(line_id))
    return out


class NextStepArgs(BaseModel):
    job_id: int
    sop_id: int


@conn.tool(
    "guide_next_step",
    description="G01 — suggest the next step / correct setup for the operator.",
    params_model=NextStepArgs,
    risk="none",
    read_only=True,
    when_to_use="To nudge the operator toward the correct next SOP step.",
)
def guide_next_step(job_id: int, sop_id: int):
    released = sop_service.released_version(sop_id)
    done = {c["step_index"] for c in sop_service.job_progress(job_id)}
    steps = (released or {}).get("steps", [])
    nxt = next((i for i in range(len(steps)) if i not in done), None)
    msg = "Tất cả bước đã xong." if nxt is None else f"Bước tiếp theo: {steps[nxt].get('name')}"
    return {"output": msg, "card": card(msg, confidence=0.75)}


class DecisionArgs(BaseModel):
    line_id: int
    reason: str


@conn.tool(
    "guide_decision_packet",
    description="G03 — surface a decision packet for the supervisor to approve (blocks -> C03).",
    params_model=DecisionArgs,
    risk="medium",
    when_to_use="When a situation needs supervisor sign-off before a command runs.",
)
def guide_decision_packet(line_id: int, reason: str):
    return {
        "output": decision_packet(
            title=f"Escalate exception on line {line_id}?",
            action="cmd_raise_exception",
            arguments={"line_id": line_id, "reason": reason},
            assumptions=[assumption(f"'{reason}' warrants supervisor escalation.", 0.7)],
        )
    }
```

Note: confirm the exact `decision_packet(...)` kwargs against `minder_python_sdk/cards.py:74` during implementation; adjust the call to the real signature (title/action/arguments/assumptions or equivalent) if it differs.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --no-sync pytest tests/test_agent_guidance.py -q`
Expected: PASS (or SKIP).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/agent/guidance.py
git add -f modules/produce/backend/tests/test_agent_guidance.py
git commit -m "feat(produce): Track B Guidance surface G01/G03 (context + decision packet)"
```

---

## Phase 7 — Guidance frontend (gated by agentEnabled)

### Task 9: Agent surface providers + G01 banner + G03 decision packet

**Files:**
- Create: `modules/produce/frontend/src/agent/GuidanceBanner.tsx`, `modules/produce/frontend/src/agent/DecisionSurface.tsx`
- Modify: `modules/produce/frontend/src/dashboard.tsx`, `modules/produce/frontend/src/main.tsx`

**Interfaces:**
- Consumes: `minder-ui-sdk` (`AgentDriverProvider`, `AgentRegistryProvider`, `DecisionPacket`, `useModuleEvents`).
- Produces: `Dashboard` accepts `agentEnabled?: boolean`; when true, wraps agent providers and renders `<GuidanceBanner>` (operator tab) + `<DecisionSurface>` (supervisor tab). `main.tsx` passes `agentEnabled={false}`.

- [ ] **Step 1: Create `frontend/src/agent/GuidanceBanner.tsx`**

```tsx
import { useEffect, useState } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';
import { api } from '../api';

// G01: shows the agent's next-step suggestion for the operator's current job.
export default function GuidanceBanner({ apiBase, jobId, sopId }: { apiBase: string; jobId: number; sopId: number }) {
  const { tokens } = useMinderTheme();
  const [msg, setMsg] = useState<string>('');
  useEffect(() => {
    api<{ output: string }>(apiBase, `/connector/tools/guide_next_step`, {
      method: 'POST', body: JSON.stringify({ arguments: { job_id: jobId, sop_id: sopId } }),
    }).then((r) => setMsg(typeof r.output === 'string' ? r.output : '')).catch(() => {});
  }, [apiBase, jobId, sopId]);
  if (!msg) return null;
  return (
    <div style={{ background: `${tokens.primary}18`, border: `1px solid ${tokens.primary}`, borderRadius: 10, padding: '10px 14px', margin: '0 0 12px', color: tokens.text, fontSize: 13 }}>
      <b style={{ color: tokens.primary }}>Gợi ý:</b> {msg}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/agent/DecisionSurface.tsx`**

```tsx
import { DecisionPacket, useModuleEvents } from 'minder-ui-sdk';

// G03: renders decision packets pushed by Minder for supervisor approval.
export default function DecisionSurface({ apiBase }: { apiBase: string }) {
  const { packets } = useModuleEvents(apiBase, 'default');
  if (!packets?.length) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      {packets.map((p: any) => (
        <DecisionPacket key={p.id ?? p.action} apiBase={apiBase} packet={p} />
      ))}
    </div>
  );
}
```

Note: confirm `useModuleEvents` return shape (`packets`) and `<DecisionPacket>` props against `minder_ui_sdk/src` during implementation; adapt names to the real API (the SDK exposes `useModuleEvents` + `DecisionPacket` per its index.ts).

- [ ] **Step 3: Modify `frontend/src/dashboard.tsx`** — add `agentEnabled` prop and conditional wrap. Add to the `Dashboard` signature `agentEnabled = false` and, when true, wrap the existing `<Surface>` subtree in `AgentDriverProvider` + `AgentRegistryProvider` (imported from `minder-ui-sdk`, apiBase `${apiBase}/connector`), and render `<DecisionSurface apiBase={apiBase+'/connector'} />` above the persona route when `tab === 'supervisor'`, and `<GuidanceBanner ... />` inside the operator route entry. Keep the non-agent path exactly as today.

- [ ] **Step 4: Modify `frontend/src/main.tsx`** — pass `agentEnabled={false}` explicitly to the standalone `<Dashboard>` render.

- [ ] **Step 5: Build gate**

Run: `cd modules/produce/frontend && npm run build`
Expected: build SUCCEEDS; dist emitted. Fix any prop/type mismatch inline against the real `minder-ui-sdk` API.

- [ ] **Step 6: Commit**

```bash
git add modules/produce/frontend/src/agent modules/produce/frontend/src/dashboard.tsx modules/produce/frontend/src/main.tsx
git commit -m "feat(produce): Track B guidance frontend (G01 banner + G03 decision surface, gated)"
```

---

## Phase 8 — Deployment

### Task 10: Backend Dockerfile installs the Python SDK

**Files:**
- Modify: `modules/produce/backend/Dockerfile`

- [ ] **Step 1: Implement** — in the python stage, before installing requirements, add (mirrors module_template):

```dockerfile
COPY minder_python_sdk /sdk
RUN pip install --no-cache-dir /sdk
```

Place these two lines after `WORKDIR /app` / apt install and before `COPY modules/produce/backend/requirements.txt`. The fe stage already copies `minder_ui_sdk`.

- [ ] **Step 2: Verify it builds**

Run: `docker build -f modules/produce/backend/Dockerfile -t produce-web .`
Expected: build SUCCEEDS.

- [ ] **Step 3: Commit**

```bash
git add modules/produce/backend/Dockerfile
git commit -m "feat(produce): install minder_python_sdk in backend image (Track B)"
```

### Task 11: Compose env to enable + announce the agent

**Files:**
- Modify: `docker-compose.yml` (the `produce-web` service)

- [ ] **Step 1: Implement** — add to `produce-web.environment` (mirrors module_template announce/Keycloak):

```yaml
      - PR_AGENT_ENABLED=1
      - MINDER_URL=http://minder:8080
      - MINDER_MODULE_CONNECTOR_URL=http://produce-web:9310
      - MINDER_MODULE_REMOTE_ENTRY=http://localhost:9310/dashboard/remoteEntry.js
      - MINDER_DEFAULT_AUTONOMY=medium
      - KEYCLOAK_TOKEN_URL=http://keycloak:8080/realms/minder/protocol/openid-connect/token
      - MINDER_MODULE_CLIENT_ID=minder-module
      - MINDER_MODULE_CLIENT_SECRET=${MINDER_MODULE_CLIENT_SECRET:-CHANGE-ME-IN-ENV}
      - MINDER_MODULE_HEARTBEAT_SEC=10
```

Change the `produce-web` healthcheck URL to `http://localhost:9310/connector/health` (the connector health path when the agent is enabled).

- [ ] **Step 2: Validate**

Run: `docker compose -f docker-compose.yml -f docker-compose.local.yml config --services | grep produce`
Expected: lists `produce-web` + `produce-worker`.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(produce): enable + announce Track B agent in compose"
```

---

## Phase 9 — Verification & docs

### Task 12: Full regression + real co-work e2e + docs

**Files:**
- Modify: `modules/produce/README.md`, `modules/module_integration.md`

- [ ] **Step 1: Full backend suite (agent disabled) + agent suite (SDK present)**

Run: `cd modules/produce/backend && uv run --no-sync pytest -q && cd ../../.. && uv run --no-sync ruff check modules/produce/backend`
Expected: Track A tests PASS; agent tests PASS if `minder_python_sdk` importable, else SKIP; ruff clean.

- [ ] **Step 2: Bring up the stack with the agent enabled**

Run: `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build produce-web produce-worker minder`
Then: `curl -s localhost:9310/connector/health` and `curl -s localhost:9310/connector/manifest | python3 -m json.tool | head -40`
Expected: health ok; manifest lists reads `read_*`, tools `cmd_*`/`guide_*`, and the 7 event types.

- [ ] **Step 3: Real co-work loop (CLAUDE.md mandate, `OPENAI_API_KEY` set)**

Drive one loop through Minder: agent reads shift OEE (`read_oee`) -> surfaces a G03 decision packet (`guide_decision_packet`) -> approve it in the supervisor UI -> confirm `cmd_raise_exception` ran (exception escalated) -> confirm the `exception.raised` envelope appears in Minder's event log. Confirm the G01 banner renders on the operator tab.

- [ ] **Step 4: Docs** — in `modules/produce/README.md` add a "Track B (Minder co-work)" section: `PR_AGENT_ENABLED`, the `/connector/*` surface, and that Track A stays standalone when disabled. In `modules/module_integration.md` update the Produce section to note the optional Track B agent surface + its announce env.

- [ ] **Step 5: Commit**

```bash
git add modules/produce/README.md modules/module_integration.md
git commit -m "docs(produce): document Track B (Minder co-work) surface + enablement"
```

---

## Self-Review

**Spec coverage:** Read R01–R07 -> Task 5. Event E01/E02/E03/E05 -> Tasks 1-2 (seam+emissions) + Task 6 (registration/forward). Command C03/C07/C09 -> Task 7. Guidance G01/G03 -> Task 8 (backend) + Task 9 (frontend). Additive/isolation + `PR_AGENT_ENABLED` regression -> Tasks 1-4. Deploy announce env -> Tasks 10-11. Testing (unit + regression + real e2e) -> Tasks throughout + Task 12. Assumption ledger + reversibility -> Task 7 (`assumption(...)`, `reversible`/`undo`) + Task 8 (decision packet assumptions).

**Placeholder scan:** No TBD/TODO. Two explicit "confirm the real signature during implementation" notes (decision_packet kwargs, useModuleEvents/DecisionPacket props) are deliberate — the exact SDK shapes are at `minder_python_sdk/cards.py:74` and `minder_ui_sdk/src/index.ts`; the implementer verifies and adapts, which is not a placeholder for logic but a guard against a signature drift.

**Type consistency:** Read names (`read_queue/read_wip/read_oee/read_downtime/read_sop/read_exceptions/read_handover`), command names (`cmd_raise_exception/cmd_draft_handover/cmd_update_production`), guidance names (`guide_next_step/guide_decision_packet`), and event kinds (`job.started/job.completed/step.confirmed/downtime.opened/downtime.closed/andon.raised/exception.raised`) are used identically across tasks, tests, manifest checks, and the e2e loop. `events.emit/subscribe/clear` and `agent.events.attach()` names are consistent. `conn.invoke(name, args)` returns `{"output": ...}` — every command/read test reads `out["output"]`.

**Scope check:** Single subsystem (Track B co-work MVP). Focused; no decomposition needed. High-risk commands and the remaining Guidance/Event waves are explicitly out of scope (spec follow-ups).
