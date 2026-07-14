# module_template Full-Stack Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Execution mode is code-all-then-verify (user preference): implement every task in order WITHOUT running tests per-task; write each task's tests alongside its code, then run the whole suite + verification once in the final Phase V.**

**Goal:** Upgrade `modules/module_template/` into a full-stack, production-shaped reference module — Celery worker, shared-Postgres data layer (own tables, read-only Minder reads), S3/MinIO media, and a four-panel advanced dashboard — while keeping its existing SDK-feature tools working.

**Architecture:** A pure-`minder_module_sdk` connector (never imports `minder`) plus its own infra clients: SQLAlchemy → the shared `minder` DB (module owns `mt_jobs`/`mt_media`, reads Minder tables read-only), boto3 → MinIO, Celery → the shared Redis (DB index `/2`). A Celery task processes jobs and reverse-pushes live progress blocks + artifacts via the SDK's `MinderClient`. Frontend is a Module-Federation remote with four panels.

**Tech Stack:** Python 3.12 + `minder_module_sdk` + SQLAlchemy 2 + psycopg2 + boto3 + Celery(redis); React 18 + Vite 5 + Module Federation; pytest (SQLite + fakes + `task_always_eager`).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-11-module-template-fullstack-design.md`.
- **The module NEVER imports `minder`** — only `minder_module_sdk` + its own deps (`sqlalchemy`, `psycopg2-binary`, `boto3`, `celery`). `MinderClient` uses httpx+env.
- **DB reuse, data isolation:** engine → `MT_DATABASE_URL` (default `postgresql://minder:minder@db:5432/minder`). The module WRITES only its own tables `mt_jobs`/`mt_media`; it READS Minder tables (`conversations`, `artifacts`) **read-only** via `text()` SELECT, each wrapped so a schema mismatch degrades to empty/zero (never 500). Own tables created with `Base.metadata.create_all(engine, checkfirst=True)` on the module's OWN metadata (never touches Minder tables — no Alembic).
- **Redis:** `MT_REDIS_URL` default `redis://redis:6379/2` (Minder uses `/0`).
- **S3:** `MT_S3_ENDPOINT` (default `http://minio:9000`), `MT_S3_BUCKET` (default `module-template`), creds `MT_S3_ACCESS_KEY`/`MT_S3_SECRET_KEY`.
- **Keep the existing 7 SDK-feature tools working** (`template_typed_query/card/block/stream/secure/async_job/export`) throughout.
- Media upload cap 25 MB → 413; bad input → 400; fail-closed SDK behavior unchanged.
- Real Minder columns (for read helpers): `conversations(id, title, mode, status, created_at, is_deleted)`, `artifacts(id, title, type, created_at, is_deleted)`.
- Port **9300**, env prefix **`MT_`**.
- **Test command:** `uv run --no-sync pytest <path>`. Module tests use SQLite/fakes + Celery `task_always_eager`; NO live infra.
- **Commits:** no `Co-Authored-By: Claude` trailer.
- **`docs/` + any `tests/` dir are gitignored (overbroad pattern) — `git add -f` for the plan AND for the module's `backend/tests/`.**
- **EXECUTION: code all tasks, then Phase V runs all tests + verify once.**

---

## File Structure

**Module — created (under `modules/module_template/`):**
- `backend/db.py` — SQLAlchemy engine, `MtJob`/`MtMedia` models, `init_db`, `db_session`, Minder read helpers.
- `backend/media.py` — boto3 S3 client (MinIO): `ensure_bucket`, `put_media`, `presigned_url`.
- `backend/celery_app.py` — Celery app + config.
- `worker/tasks.py` — the `run_job` Celery task (DB updates + reverse-push + artifact).
- `worker/Dockerfile` — celery worker image.
- `backend/tests/test_db.py`, `test_media.py`, `test_jobs.py` (extend `test_template.py`).
- `frontend/src/panels/{JobsPanel,MediaPanel,DataPanel,MetricsPanel}.tsx`, `frontend/src/Chart.tsx`.

**Module — modified:**
- `backend/app.py` — new tools + routes + readiness probe.
- `backend/requirements.txt` — real deps.
- `backend/Dockerfile` — install requirements.
- `frontend/src/DashboardApp.tsx` — tabbed 4-panel shell (keep ShowcaseBlock).
- `frontend/vite.config.ts` — unchanged exposes (Dashboard + ShowcaseBlock).
- `SKILL.md`, `manifest.json`, `docker-compose.snippet.yml`, `README.md`.

---

# Phase D — Data layer

### Task D1: `backend/db.py` — engine, models, read helpers

**Files:**
- Create: `modules/module_template/backend/db.py`
- Modify: `modules/module_template/backend/requirements.txt`
- Test: `modules/module_template/backend/tests/test_db.py`

**Interfaces:**
- Produces: `engine`, `SessionLocal`, `Base`; models `MtJob`, `MtMedia`; `init_db() -> None`;
  `db_session()` (contextmanager yielding a Session); read helpers
  `list_conversations(limit=10) -> list[dict]`, `count_artifacts() -> int`,
  `recent_artifacts(limit=10) -> list[dict]` (each degrade to `[]`/`0` on error).

- [ ] **Step 1: Implement** `modules/module_template/backend/db.py`:

```python
"""module_template data layer. Reuses the shared `minder` Postgres INSTANCE but
owns only the mt_* tables; reads Minder tables read-only. Never imports `minder`."""
from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
from typing import Iterator

from sqlalchemy import (Column, DateTime, Integer, String, Text, create_engine, text)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

logger = logging.getLogger("module_template.db")

MT_DATABASE_URL = os.environ.get("MT_DATABASE_URL", "postgresql://minder:minder@db:5432/minder")

engine = create_engine(MT_DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
Base = declarative_base()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class MtJob(Base):
    __tablename__ = "mt_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(64), nullable=False, default="demo")
    status = Column(String(16), nullable=False, default="queued")  # queued|running|done|error
    pct = Column(Integer, nullable=False, default=0)
    params_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status, "pct": self.pct,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class MtMedia(Base):
    __tablename__ = "mt_media"
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    s3_key = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    def as_dict(self) -> dict:
        return {"id": self.id, "filename": self.filename, "s3_key": self.s3_key,
                "content_type": self.content_type, "size": self.size,
                "created_at": self.created_at.isoformat() if self.created_at else None}


def init_db() -> None:
    """Create ONLY the module's own mt_* tables (checkfirst). Never touches Minder tables."""
    Base.metadata.create_all(engine, checkfirst=True)


@contextlib.contextmanager
def db_session() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# --- read-only Minder reads (best-effort; degrade on schema drift) ---------------
def list_conversations(limit: int = 10) -> list[dict]:
    sql = text("SELECT id, title, mode, status, created_at FROM conversations "
               "WHERE is_deleted = false ORDER BY id DESC LIMIT :limit")
    try:
        with engine.connect() as c:
            return [dict(r._mapping) | {"created_at": str(r._mapping["created_at"])}
                    for r in c.execute(sql, {"limit": limit})]
    except Exception as exc:  # noqa: BLE001 — read-only best-effort
        logger.warning("read conversations failed (degrading): %s", exc)
        return []


def count_artifacts() -> int:
    try:
        with engine.connect() as c:
            return int(c.execute(text("SELECT count(*) FROM artifacts WHERE is_deleted = false")).scalar() or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("count artifacts failed (degrading): %s", exc)
        return 0


def recent_artifacts(limit: int = 10) -> list[dict]:
    sql = text("SELECT id, title, type, created_at FROM artifacts WHERE is_deleted = false "
               "ORDER BY id DESC LIMIT :limit")
    try:
        with engine.connect() as c:
            return [dict(r._mapping) | {"created_at": str(r._mapping["created_at"])}
                    for r in c.execute(sql, {"limit": limit})]
    except Exception as exc:  # noqa: BLE001
        logger.warning("read artifacts failed (degrading): %s", exc)
        return []
```

- [ ] **Step 2: `requirements.txt`** — set `modules/module_template/backend/requirements.txt` to:

```text
sqlalchemy>=2.0
psycopg2-binary>=2.9
boto3>=1.34
celery[redis]>=5.3
```

- [ ] **Step 3: Test** `modules/module_template/backend/tests/test_db.py` — use in-memory SQLite by overriding the engine BEFORE import is impractical; instead test the models + degrade path with a dedicated SQLite engine:

```python
import importlib
import os


def test_models_roundtrip_on_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import backend_db  # noqa: F401 — see conftest note below
```

*(Note: `db.py` binds `engine` at import time from `MT_DATABASE_URL`, so the test MUST set the env before importing. Add a `modules/module_template/backend/tests/conftest.py` that inserts the backend dir on `sys.path`; import `db` fresh inside each test after setting the env, e.g. `import importlib, sys; sys.path.insert(0, backend_dir); db = importlib.import_module("db"); importlib.reload(db)`. Write the test as:)*

```python
import importlib
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)


def _fresh_db(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import db
    importlib.reload(db)
    db.init_db()
    return db


def test_mtjob_roundtrip(monkeypatch, tmp_path):
    db = _fresh_db(monkeypatch, tmp_path)
    with db.db_session() as s:
        s.add(db.MtJob(kind="demo", status="queued", pct=0))
    with db.db_session() as s:
        row = s.query(db.MtJob).one()
        assert row.status == "queued" and row.as_dict()["pct"] == 0


def test_minder_reads_degrade_when_tables_absent(monkeypatch, tmp_path):
    # SQLite has no `conversations`/`artifacts` tables → helpers must degrade, not raise.
    db = _fresh_db(monkeypatch, tmp_path)
    assert db.list_conversations() == []
    assert db.count_artifacts() == 0
    assert db.recent_artifacts() == []
```

- [ ] **Step 4: Commit** — `git add modules/module_template/backend/db.py modules/module_template/backend/requirements.txt && git add -f modules/module_template/backend/tests/test_db.py && git commit -m "feat(module_template): data layer — mt_jobs/mt_media models + read-only Minder helpers"`.

---

# Phase S — Media store

### Task S1: `backend/media.py` — S3/MinIO client

**Files:**
- Create: `modules/module_template/backend/media.py`
- Test: `modules/module_template/backend/tests/test_media.py`

**Interfaces:**
- Consumes: `db.db_session`, `db.MtMedia` (Task D1).
- Produces: `s3_client()`, `ensure_bucket()`, `put_media(filename, data: bytes, content_type) -> dict`
  (writes S3 + an `mt_media` row, returns the row dict), `presigned_url(s3_key, expires=3600) -> str`.

- [ ] **Step 1: Implement** `modules/module_template/backend/media.py`:

```python
"""module_template S3/MinIO media store. boto3 only; never imports `minder`."""
from __future__ import annotations

import logging
import os
import uuid

import boto3
from botocore.client import Config

import db

logger = logging.getLogger("module_template.media")

MT_S3_ENDPOINT = os.environ.get("MT_S3_ENDPOINT", "http://minio:9000")
MT_S3_BUCKET = os.environ.get("MT_S3_BUCKET", "module-template")
MT_S3_ACCESS_KEY = os.environ.get("MT_S3_ACCESS_KEY", "minioadmin")
MT_S3_SECRET_KEY = os.environ.get("MT_S3_SECRET_KEY", "minioadmin")


def s3_client():
    return boto3.client("s3", endpoint_url=MT_S3_ENDPOINT,
                        aws_access_key_id=MT_S3_ACCESS_KEY,
                        aws_secret_access_key=MT_S3_SECRET_KEY,
                        config=Config(signature_version="s3v4"))


def ensure_bucket() -> None:
    c = s3_client()
    try:
        c.head_bucket(Bucket=MT_S3_BUCKET)
    except Exception:  # noqa: BLE001 — create when missing
        c.create_bucket(Bucket=MT_S3_BUCKET)


def put_media(filename: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
    key = f"{uuid.uuid4().hex}/{filename}"
    s3_client().put_object(Bucket=MT_S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    with db.db_session() as s:
        row = db.MtMedia(filename=filename, s3_key=key, content_type=content_type, size=len(data))
        s.add(row)
        s.flush()
        return row.as_dict()


def presigned_url(s3_key: str, expires: int = 3600) -> str:
    return s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": MT_S3_BUCKET, "Key": s3_key}, ExpiresIn=expires)
```

- [ ] **Step 2: Test** `modules/module_template/backend/tests/test_media.py` — stub boto3 so no live S3:

```python
import importlib
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)


class _FakeS3:
    def __init__(self): self.objects = {}
    def head_bucket(self, Bucket): pass
    def create_bucket(self, Bucket): pass
    def put_object(self, Bucket, Key, Body, ContentType): self.objects[Key] = Body
    def generate_presigned_url(self, op, Params, ExpiresIn): return f"http://minio/{Params['Key']}?sig=x"


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import db, media
    importlib.reload(db); importlib.reload(media)
    db.init_db()
    fake = _FakeS3()
    monkeypatch.setattr(media, "s3_client", lambda: fake)
    return db, media, fake


def test_put_media_writes_s3_and_row(monkeypatch, tmp_path):
    db, media, fake = _fresh(monkeypatch, tmp_path)
    row = media.put_media("hello.txt", b"hi", "text/plain")
    assert row["filename"] == "hello.txt" and row["size"] == 2
    assert any(k.endswith("/hello.txt") for k in fake.objects)
    with db.db_session() as s:
        assert s.query(db.MtMedia).count() == 1


def test_presigned_url(monkeypatch, tmp_path):
    _db, media, _fake = _fresh(monkeypatch, tmp_path)
    assert media.presigned_url("k/hello.txt").startswith("http://minio/")
```

- [ ] **Step 3: Commit** — `git add modules/module_template/backend/media.py && git add -f modules/module_template/backend/tests/test_media.py && git commit -m "feat(module_template): S3/MinIO media store (put_media + presigned_url)"`.

---

# Phase W — Celery worker

### Task W1: `backend/celery_app.py` — Celery app

**Files:**
- Create: `modules/module_template/backend/celery_app.py`

**Interfaces:**
- Produces: `celery_app` (a `Celery`), broker/backend from `MT_REDIS_URL`. When `MT_TEST=1`,
  `task_always_eager=True` + `task_eager_propagates=True`.

- [ ] **Step 1: Implement** `modules/module_template/backend/celery_app.py`:

```python
"""module_template Celery app — reuses the shared Redis INSTANCE at DB index /2."""
from __future__ import annotations

import os

from celery import Celery

MT_REDIS_URL = os.environ.get("MT_REDIS_URL", "redis://redis:6379/2")

celery_app = Celery("module_template", broker=MT_REDIS_URL, backend=MT_REDIS_URL,
                    include=["tasks"])
celery_app.conf.update(task_track_started=True, result_expires=3600)
if os.environ.get("MT_TEST") == "1":
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
```

- [ ] **Step 2: Commit** — `git add modules/module_template/backend/celery_app.py && git commit -m "feat(module_template): Celery app on shared Redis /2"`.

### Task W2: `worker/tasks.py` — the `run_job` task

**Files:**
- Create: `modules/module_template/worker/tasks.py`, `modules/module_template/backend/tasks.py` (thin re-export so both `backend` and `worker` import the same task)
- Test: `modules/module_template/backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `celery_app` (W1), `db` (D1), `minder_module_sdk` (`Connector`/`MinderClient`).
- Produces: `run_job(job_id: int, session_id: str | None, steps: int) -> dict` (a Celery task). It
  updates the `MtJob` (running → pct per step → done), reverse-pushes a live block via
  `MinderClient` when `session_id` + config are present (best-effort), and marks `error` on failure.

- [ ] **Step 1: Implement** `modules/module_template/backend/tasks.py` (the real task lives here so
  `backend` can enqueue it and the `worker` can run it; the worker's Dockerfile sets `PYTHONPATH`
  to the backend dir):

```python
"""The module_template background task. Runs in the Celery worker; updates the
DB, reverse-pushes a live progress block, and attaches a result artifact. Uses
the SDK's MinderClient — never imports `minder`."""
from __future__ import annotations

import json
import logging
import time

from celery_app import celery_app
import db

logger = logging.getLogger("module_template.tasks")


def _client():
    """Build an MinderClient from env (announce config); None if unconfigured."""
    from minder_module_sdk.announce import resolve_announce_config
    from minder_module_sdk.client import MinderClient
    cfg = resolve_announce_config()
    return MinderClient("module_template", cfg) if cfg is not None else None


@celery_app.task(name="module_template.run_job")
def run_job(job_id: int, session_id: str | None, steps: int) -> dict:
    steps = max(1, int(steps))
    with db.db_session() as s:
        job = s.get(db.MtJob, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        job.status = "running"; job.pct = 0

    client = _client() if session_id else None
    bid = None
    try:
        if client and session_id:
            bid = client.push_block(session_id, "./ShowcaseBlock", {"kind": "job", "pct": 0})
        for i in range(1, steps + 1):
            time.sleep(1)
            pct = int(i / steps * 100)
            with db.db_session() as s:
                job = s.get(db.MtJob, job_id)
                job.pct = pct; job.status = "running" if i < steps else "done"
            if client and session_id and bid:
                try:
                    client.update_block(session_id, bid, {"kind": "job", "pct": pct, "done": i == steps})
                except Exception as exc:  # noqa: BLE001 — reverse-push best-effort
                    logger.warning("run_job block update failed: %s", exc)
        with db.db_session() as s:
            job = s.get(db.MtJob, job_id)
            job.status = "done"; job.result_json = json.dumps({"steps": steps})
        if client and session_id:
            try:
                client.push_artifact(session_id, f"job_{job_id}_report.md",
                                     f"# Job {job_id}\n\ncompleted {steps} steps.\n".encode())
            except Exception as exc:  # noqa: BLE001
                logger.warning("run_job artifact push failed: %s", exc)
        return {"ok": True, "job_id": job_id}
    except Exception as exc:  # noqa: BLE001 — mark error, never crash the worker
        logger.exception("run_job failed")
        with db.db_session() as s:
            job = s.get(db.MtJob, job_id)
            if job:
                job.status = "error"; job.result_json = json.dumps({"error": str(exc)})
        return {"ok": False, "error": str(exc)}
```

- [ ] **Step 2:** create `modules/module_template/worker/tasks.py` as a thin re-export so a
  `celery -A tasks worker` started from the worker dir finds it:

```python
"""Worker entrypoint module — re-exports the task defined in the backend package.
The worker image sets PYTHONPATH to the backend dir so `import tasks` resolves there."""
from tasks import celery_app, run_job  # noqa: F401
```

*(If PYTHONPATH resolution makes the re-export circular, the worker Dockerfile instead runs
`celery -A tasks worker` with the backend dir on PYTHONPATH and this file is unnecessary — the
implementer picks whichever is cleaner and notes it. The canonical task is `backend/tasks.py`.)*

- [ ] **Step 3: Test** `modules/module_template/backend/tests/test_jobs.py` — eager mode + fake client:

```python
import importlib
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_TEST", "1")
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import db, celery_app, tasks
    importlib.reload(db); importlib.reload(celery_app); importlib.reload(tasks)
    db.init_db()
    return db, tasks


def test_run_job_completes_and_updates_db(monkeypatch, tmp_path):
    db, tasks = _fresh(monkeypatch, tmp_path)
    monkeypatch.setattr(tasks, "_client", lambda: None)      # no reverse-push in unit test
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)  # fast
    with db.db_session() as s:
        s.add(db.MtJob(id=1, kind="demo", status="queued", pct=0))
    res = tasks.run_job.apply(args=(1, None, 2)).get()  # eager
    assert res["ok"] is True
    with db.db_session() as s:
        assert s.get(db.MtJob, 1).status == "done"


def test_run_job_reverse_pushes_when_session(monkeypatch, tmp_path):
    db, tasks = _fresh(monkeypatch, tmp_path)
    pushed = {"updates": 0, "artifact": 0}

    class _FakeClient:
        def push_block(self, sid, comp, props): return "b1"
        def update_block(self, sid, bid, props): pushed["updates"] += 1
        def push_artifact(self, sid, name, data): pushed["artifact"] += 1; return 9

    monkeypatch.setattr(tasks, "_client", lambda: _FakeClient())
    monkeypatch.setattr(tasks.time, "sleep", lambda *_: None)
    with db.db_session() as s:
        s.add(db.MtJob(id=1, kind="demo", status="queued", pct=0))
    tasks.run_job.apply(args=(1, "sess-1", 3)).get()
    assert pushed["updates"] == 3 and pushed["artifact"] == 1
```

- [ ] **Step 4: Commit** — `git add modules/module_template/backend/tasks.py modules/module_template/worker/tasks.py && git add -f modules/module_template/backend/tests/test_jobs.py && git commit -m "feat(module_template): run_job Celery task — DB updates + reverse-push block + artifact"`.

---

# Phase A — Backend tools & routes

### Task A1: extend `backend/app.py` — DB/media/job tools, routes, readiness

**Files:**
- Modify: `modules/module_template/backend/app.py`
- Test: `modules/module_template/backend/tests/test_template.py` (extend)

**Interfaces:**
- Consumes: `db`, `media`, `tasks` (D1/S1/W2); the existing `conn` + 7 tools.
- Produces: tools `template_start_job`, `template_list_jobs`, `template_db_overview`; routes
  `/jobs`, `/jobs/{id}`, `/media`, `/media/upload`, `/overview`, `/metrics`; a readiness probe
  checking DB+Redis+S3+Celery.

- [ ] **Step 1: Add imports + `on_startup` DB/bucket init** near the top of `app.py` (after the
  existing imports):

```python
import db
import media
import tasks


@conn.on_startup
def _init_infra() -> None:
    try:
        db.init_db()
        media.ensure_bucket()
        logger.info("module_template infra ready (db + bucket)")
    except Exception as exc:  # noqa: BLE001 — readiness reports not-ready if this fails
        logger.warning("infra init failed (will report not-ready): %s", exc)
```

- [ ] **Step 2: Add the new tools** (after the existing 7):

```python
@conn.tool("template_start_job",
           description="Start a background job (Celery). Watch a live progress block update.",
           parameters={"type": "object", "properties": {"steps": {"type": "integer"}}})
def template_start_job(steps: int = 3, session_id=None):
    with db.db_session() as s:
        job = db.MtJob(kind="demo", status="queued", pct=0)
        s.add(job); s.flush()
        job_id = job.id
    tasks.run_job.delay(job_id, session_id, int(steps))
    return {"output": f"started job #{job_id} ({steps} steps) — watch the block update live.",
            "card": card(f"Job #{job_id} queued.", card_type="template_card")}


@conn.tool("template_list_jobs", description="List recent background jobs.")
def template_list_jobs():
    with db.db_session() as s:
        rows = [j.as_dict() for j in s.query(db.MtJob).order_by(db.MtJob.id.desc()).limit(10)]
    return {"output": {"jobs": rows}}


@conn.tool("template_db_overview",
           description="Module DB counts + read-only Minder aggregates (shared database).")
def template_db_overview():
    with db.db_session() as s:
        jobs = s.query(db.MtJob).count()
        mediac = s.query(db.MtMedia).count()
    return {"output": {"mt_jobs": jobs, "mt_media": mediac,
                       "minder_conversations": db.list_conversations(5),
                       "minder_artifacts_count": db.count_artifacts()}}
```

- [ ] **Step 3: Add the dashboard routes.** Add (using `@conn.route`; note `app.py` already
  imports what it needs — add `from fastapi import Request, UploadFile` where used):

```python
@conn.route("/jobs", methods=["GET"])
def route_jobs():
    with db.db_session() as s:
        return {"jobs": [j.as_dict() for j in s.query(db.MtJob).order_by(db.MtJob.id.desc()).limit(50)]}


@conn.route("/media", methods=["GET"])
def route_media():
    with db.db_session() as s:
        rows = [m.as_dict() for m in s.query(db.MtMedia).order_by(db.MtMedia.id.desc()).limit(50)]
    for r in rows:
        r["url"] = media.presigned_url(r["s3_key"])
    return {"media": rows}


@conn.route("/media/upload", methods=["POST"])
def route_media_upload(body):
    # body carries {"filename", "content_b64", "content_type"} (dashboard posts JSON;
    # the SDK route handler receives the parsed JSON body).
    import base64
    from fastapi import HTTPException
    data = base64.b64decode(body.get("content_b64", ""))
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "file too large (max 25MB)")
    if not body.get("filename"):
        raise HTTPException(400, "filename required")
    return media.put_media(body["filename"], data, body.get("content_type", "application/octet-stream"))


@conn.route("/overview", methods=["GET"])
def route_overview():
    with db.db_session() as s:
        return {"mt_jobs": s.query(db.MtJob).count(), "mt_media": s.query(db.MtMedia).count(),
                "minder_conversations": db.list_conversations(10),
                "minder_artifacts_count": db.count_artifacts(),
                "minder_recent_artifacts": db.recent_artifacts(10)}


@conn.route("/metrics", methods=["GET"])
def route_metrics():
    with db.db_session() as s:
        by_status: dict = {}
        for (st,) in s.query(db.MtJob.status).all():
            by_status[st] = by_status.get(st, 0) + 1
        total_bytes = sum(m.size for m in s.query(db.MtMedia).all())
    return {"jobs_by_status": by_status, "media_total_bytes": total_bytes}
```

- [ ] **Step 4: Replace the readiness probe** `_ready` with a real one checking all four deps:

```python
@conn.readiness_probe
def _ready():
    checks = {"db": False, "redis": False, "s3": False, "celery": False}
    try:
        with db.engine.connect() as c:
            c.exec_driver_sql("SELECT 1"); checks["db"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        import redis  # celery[redis] pulls this in
        redis.Redis.from_url(tasks.celery_app.conf.broker_url).ping(); checks["redis"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        media.s3_client().head_bucket(Bucket=media.MT_S3_BUCKET); checks["s3"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        checks["celery"] = bool(tasks.celery_app.control.ping(timeout=1))
    except Exception:  # noqa: BLE001
        pass
    return {"ready": all(checks.values()), "detail": checks}
```

*(Keep the existing `_health` probe. The `service.warm_up`/`is_warm` from the light version may be
removed if unused now — the implementer removes it only if nothing references it, else leaves it.)*

- [ ] **Step 5: Extend tests** in `modules/module_template/backend/tests/test_template.py` — add
  (import `db`, set `MT_TEST=1` + a SQLite `MT_DATABASE_URL` + monkeypatch `media`/`tasks` at
  import time via the same fresh-import pattern used in `test_jobs.py`; keep the existing tests):

```python
def test_start_and_list_jobs(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_TEST", "1")
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import importlib, db as _db
    importlib.reload(_db); _db.init_db()
    import app as mt; importlib.reload(mt)
    monkeypatch.setattr(mt.tasks.run_job, "delay", lambda *a, **k: None)
    out = mt.conn.invoke("template_start_job", {"steps": 2})
    assert "started job" in out["output"]
    lst = mt.conn.invoke("template_list_jobs", {})
    assert len(lst["output"]["jobs"]) == 1
```

- [ ] **Step 6: Commit** — `git add modules/module_template/backend/app.py && git add -f modules/module_template/backend/tests/test_template.py && git commit -m "feat(module_template): job/media/db tools + dashboard routes + real readiness probe"`.

---

# Phase F — Frontend (4 panels)

### Task F1: tabbed dashboard + four panels

**Files:**
- Create: `modules/module_template/frontend/src/panels/JobsPanel.tsx`, `MediaPanel.tsx`, `DataPanel.tsx`, `MetricsPanel.tsx`, `modules/module_template/frontend/src/Chart.tsx`
- Modify: `modules/module_template/frontend/src/DashboardApp.tsx`

**Interfaces:**
- Consumes: the connector routes from A1 via `apiBase`.

- [ ] **Step 1: `src/Chart.tsx`** — a tiny dependency-free bar chart:

```tsx
export function BarChart({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(1, ...data.map(d => d.value));
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', height: 120 }}>
      {data.map(d => (
        <div key={d.label} style={{ textAlign: 'center', flex: 1 }}>
          <div style={{ height: `${(d.value / max) * 100}px`, background: '#6366f1', borderRadius: 4 }} />
          <div style={{ fontSize: 11 }}>{d.label}</div>
          <div style={{ fontSize: 11, opacity: 0.7 }}>{d.value}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: `src/panels/JobsPanel.tsx`** — live job table (polls `/connector/jobs` every 2s):

```tsx
import { useEffect, useState } from 'react';

export function JobsPanel({ apiBase }: { apiBase: string }) {
  const [jobs, setJobs] = useState<any[]>([]);
  const load = () => fetch(`${apiBase}/connector/jobs`).then(r => r.json())
    .then(d => setJobs(d.jobs || [])).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 2000); return () => clearInterval(t); }, [apiBase]);
  return (
    <div>
      <h3>Jobs</h3>
      <table><thead><tr><th>id</th><th>kind</th><th>status</th><th>pct</th></tr></thead>
        <tbody>{jobs.map(j => (
          <tr key={j.id}><td>{j.id}</td><td>{j.kind}</td><td>{j.status}</td><td>{j.pct}%</td></tr>
        ))}</tbody></table>
    </div>
  );
}
```

- [ ] **Step 3: `src/panels/MediaPanel.tsx`** — upload + gallery:

```tsx
import { useEffect, useState } from 'react';

export function MediaPanel({ apiBase }: { apiBase: string }) {
  const [items, setItems] = useState<any[]>([]);
  const load = () => fetch(`${apiBase}/connector/media`).then(r => r.json())
    .then(d => setItems(d.media || [])).catch(() => {});
  useEffect(() => { load(); }, [apiBase]);
  const upload = async (file: File) => {
    const b64 = btoa(String.fromCharCode(...new Uint8Array(await file.arrayBuffer())));
    await fetch(`${apiBase}/connector/media/upload`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, content_b64: b64, content_type: file.type }),
    });
    load();
  };
  return (
    <div>
      <h3>Media</h3>
      <input type="file" onChange={e => e.target.files && upload(e.target.files[0])} />
      <ul>{items.map(m => <li key={m.id}><a href={m.url} target="_blank">{m.filename}</a> ({m.size}b)</li>)}</ul>
    </div>
  );
}
```

- [ ] **Step 4: `src/panels/DataPanel.tsx`** — module counts + read-only Minder conversations:

```tsx
import { useEffect, useState } from 'react';

export function DataPanel({ apiBase }: { apiBase: string }) {
  const [ov, setOv] = useState<any>({});
  useEffect(() => { fetch(`${apiBase}/connector/overview`).then(r => r.json()).then(setOv).catch(() => {}); }, [apiBase]);
  return (
    <div>
      <h3>Data</h3>
      <p>mt_jobs: {ov.mt_jobs ?? '…'} · mt_media: {ov.mt_media ?? '…'} · minder artifacts: {ov.minder_artifacts_count ?? '…'}</p>
      <h4>Minder conversations (read-only)</h4>
      <ul>{(ov.minder_conversations || []).map((c: any) => <li key={c.id}>#{c.id} {c.title || '(untitled)'} — {c.status}</li>)}</ul>
    </div>
  );
}
```

- [ ] **Step 5: `src/panels/MetricsPanel.tsx`** — charts from `/metrics`:

```tsx
import { useEffect, useState } from 'react';
import { BarChart } from '../Chart';

export function MetricsPanel({ apiBase }: { apiBase: string }) {
  const [m, setM] = useState<any>({});
  useEffect(() => { fetch(`${apiBase}/connector/metrics`).then(r => r.json()).then(setM).catch(() => {}); }, [apiBase]);
  const bars = Object.entries(m.jobs_by_status || {}).map(([label, value]) => ({ label, value: value as number }));
  return (
    <div>
      <h3>Metrics</h3>
      <h4>Jobs by status</h4>
      <BarChart data={bars.length ? bars : [{ label: 'none', value: 0 }]} />
      <p>Media stored: {((m.media_total_bytes || 0) / 1024).toFixed(1)} KB</p>
    </div>
  );
}
```

- [ ] **Step 6: Rewrite `src/DashboardApp.tsx`** as a tabbed shell:

```tsx
import { useState } from 'react';
import { JobsPanel } from './panels/JobsPanel';
import { MediaPanel } from './panels/MediaPanel';
import { DataPanel } from './panels/DataPanel';
import { MetricsPanel } from './panels/MetricsPanel';

const TABS = ['Jobs', 'Media', 'Data', 'Metrics'] as const;

export default function DashboardApp({ apiBase }: { apiBase: string }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Jobs');
  return (
    <div style={{ padding: 16, fontFamily: 'system-ui' }}>
      <h2>module_template — full-stack showcase</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
                  style={{ fontWeight: tab === t ? 700 : 400 }}>{t}</button>
        ))}
      </div>
      {tab === 'Jobs' && <JobsPanel apiBase={apiBase} />}
      {tab === 'Media' && <MediaPanel apiBase={apiBase} />}
      {tab === 'Data' && <DataPanel apiBase={apiBase} />}
      {tab === 'Metrics' && <MetricsPanel apiBase={apiBase} />}
    </div>
  );
}
```

- [ ] **Step 7:** `ShowcaseBlock.tsx` and `vite.config.ts` are UNCHANGED (Dashboard + ShowcaseBlock still exposed).

- [ ] **Step 8: Commit** — `git add modules/module_template/frontend/ && git commit -m "feat(module_template): 4-panel advanced dashboard (jobs/media/data/metrics)"`.

---

# Phase M — Deploy & docs

### Task M1: Dockerfiles, compose, SKILL/manifest/README

**Files:**
- Modify: `modules/module_template/backend/Dockerfile`, `modules/module_template/docker-compose.snippet.yml`, `modules/module_template/README.md`, `modules/module_template/SKILL.md`
- Create: `modules/module_template/worker/Dockerfile`

- [ ] **Step 1: `backend/Dockerfile`** — ensure it installs requirements (add the `pip install -r requirements.txt` line if the light version skipped it):

```dockerfile
# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY modules/module_template/frontend/package.json modules/module_template/frontend/package-lock.json* ./
RUN npm install
COPY modules/module_template/frontend/ ./
RUN npm run build

# --- python service stage ---
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY minder_module_sdk /sdk
RUN pip install --no-cache-dir /sdk
COPY modules/module_template/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/module_template/backend/ /app
COPY --from=fe /fe/dist /app/frontend_dist
ENV PYTHONUNBUFFERED=1 MT_PUBLIC_BASE=http://localhost:9300
EXPOSE 9300
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9300"]
```

- [ ] **Step 2: `worker/Dockerfile`** — celery worker (reuses the backend code):

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY minder_module_sdk /sdk
RUN pip install --no-cache-dir /sdk
COPY modules/module_template/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/module_template/backend/ /app
ENV PYTHONUNBUFFERED=1
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
```

- [ ] **Step 3: `docker-compose.snippet.yml`** — minio + web + worker (reuse `db` + `redis`):

```yaml
# Paste into docker-compose.yml (same network as `minder`). Build context = repo root.
  minio:
    image: minio/minio:latest
    command: ["server", "/data", "--console-address", ":9001"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports: ["9000:9000", "9001:9001"]
    volumes: ["module_template_media:/data"]

  module-template-web:
    build: { context: ., dockerfile: modules/module_template/backend/Dockerfile }
    ports: ["9300:9300"]
    depends_on: [db, redis, minio]
    environment:
      MINDER_URL: "http://minder:8000"
      MINDER_MODULE_CONNECTOR_URL: "http://module-template-web:9300"
      MINDER_MODULE_REMOTE_ENTRY: "http://localhost:9300/dashboard/remoteEntry.js"
      MT_PUBLIC_BASE: "http://localhost:9300"
      MT_DATABASE_URL: "postgresql://minder:minder@db:5432/minder"
      MT_REDIS_URL: "redis://redis:6379/2"
      MT_S3_ENDPOINT: "http://minio:9000"
      MT_S3_BUCKET: "module-template"
      MT_S3_ACCESS_KEY: "minioadmin"
      MT_S3_SECRET_KEY: "minioadmin"
      KEYCLOAK_TOKEN_URL: "http://keycloak:8080/realms/minder/protocol/openid-connect/token"
      MINDER_MODULE_CLIENT_ID: "minder-module"
      MINDER_MODULE_CLIENT_SECRET: "CHANGE-ME-IN-ENV"

  module-template-worker:
    build: { context: ., dockerfile: modules/module_template/worker/Dockerfile }
    depends_on: [db, redis, minio]
    environment:
      MT_DATABASE_URL: "postgresql://minder:minder@db:5432/minder"
      MT_REDIS_URL: "redis://redis:6379/2"
      MT_S3_ENDPOINT: "http://minio:9000"
      MT_S3_BUCKET: "module-template"
      MT_S3_ACCESS_KEY: "minioadmin"
      MT_S3_SECRET_KEY: "minioadmin"
      # Reverse-push from the worker needs announce env + module-push creds:
      MINDER_URL: "http://minder:8000"
      MINDER_MODULE_CONNECTOR_URL: "http://module-template-web:9300"
      MINDER_MODULE_REMOTE_ENTRY: "http://localhost:9300/dashboard/remoteEntry.js"
      KEYCLOAK_TOKEN_URL: "http://keycloak:8080/realms/minder/protocol/openid-connect/token"
      MINDER_MODULE_CLIENT_ID: "minder-module"
      MINDER_MODULE_CLIENT_SECRET: "CHANGE-ME-IN-ENV"
```

Add `module_template_media:` under the top-level `volumes:` in `docker-compose.yml` (note in the snippet).

- [ ] **Step 4: Update `README.md`** — add a "Full-stack architecture" section: the infra-reuse map (shared `db`/`redis`, own `mt_*` tables, read-only Minder reads, MinIO bucket, Celery on `/2`), the four panels, and a prominent **isolation caveat** ("reuses the `minder` database; writes only `mt_*`, reads Minder tables read-only and degrades on schema drift; do NOT write Minder's tables from a module"). Map the new features to code (`db.py`, `media.py`, `tasks.py`, the routes, the panels).

- [ ] **Step 5: Update `SKILL.md`** — add the new tools (`template_start_job`, `template_list_jobs`, `template_db_overview`) to the when/how-to-use list, and note the dashboard's Jobs/Media/Data/Metrics panels.

- [ ] **Step 6: Update `manifest.json`** — bump `dashboard.default_height` (e.g. 760) for the panels; keep the `remote` block (Dashboard + ShowcaseBlock).

- [ ] **Step 7: Commit** — `git add modules/module_template/ && git commit -m "feat(module_template): Dockerfiles, minio+web+worker compose, README/SKILL/manifest for full-stack"`.

---

# Phase V — Verify (run once, at the end)

- [ ] **Step 1: Module Python tests** (SQLite + fakes + eager Celery — no live infra)

Run: `MT_TEST=1 uv run --no-sync pytest modules/module_template/backend/tests/ -v`
Expected: all PASS (db round-trip + Minder-read degrade, media put/presign, run_job eager + reverse-push, start/list jobs, plus the kept SDK-feature tests).

- [ ] **Step 2: Full Python suite (no regressions)**

Run: `uv run --no-sync pytest -q --ignore=tests/search/test_enterprise_acl.py --ignore=tests/search/test_stores.py`
Expected: no new failures vs baseline (pre-existing enterprise-knowledge/qdrant failures unrelated; the module tests are collected from `modules/module_template/backend/tests/`).

- [ ] **Step 3: Lint**

Run: `uv run --no-sync ruff check modules/module_template/backend/ modules/module_template/worker/`
Expected: clean.

- [ ] **Step 4: Frontend build**

Run: `cd modules/module_template/frontend && npm install && npm run build`
Expected: clean MF build producing `dist/remoteEntry.js` (Dashboard + panels + ShowcaseBlock chunks).

- [ ] **Step 5: E2E (deferred to user — needs the compose stack + `OPENAI_API_KEY`, per CLAUDE.md)**

`docker compose up -d --build minio module-template-web module-template-worker`, then: ask the agent
to `template_start_job` and watch the live progress block + the report artifact; upload a file in the
Media panel and see it in the gallery; open Data/Metrics and confirm the module counts + read-only
Minder conversation/artifact aggregates render; confirm the module's tools stay hidden until DB+Redis+S3+worker are all up (readiness gate).

- [ ] **Step 6: Commit** any verification fixups.

---

## Self-Review Notes

- **Spec coverage:** data layer (D1) · media (S1) · Celery app (W1) · run_job task with reverse-push + artifact (W2) · job/media/db tools + routes + readiness (A1) · four frontend panels (F1) · Dockerfiles/compose/docs (M1). Every spec component maps to a task; the existing 7 SDK-feature tools are preserved in A1.
- **Type/name consistency:** `MtJob`/`MtMedia` + `.as_dict()` used identically in db/media/tasks/app/tests. `run_job(job_id, session_id, steps)` signature matches between `tasks.py`, the `template_start_job` enqueue, and the eager test. Route paths (`/jobs`, `/media`, `/media/upload`, `/overview`, `/metrics`) match between `app.py` and the frontend panels' `fetch` calls. `MT_*` env names consistent across db/media/celery/compose. `MinderClient(module, cfg)` + `resolve_announce_config()` match the SDK.
- **No-minder-import:** db/media/celery/tasks/app import only `minder_module_sdk` (+ `sqlalchemy`/`boto3`/`celery`/stdlib) — never `minder`.
- **Deviation from spec (flagged):** own-tables created via `Base.metadata.create_all(checkfirst=True)` instead of Alembic — simpler and strictly safer on a shared DB (only ever creates the module's own metadata). Documented in db.py + README.
- **Reconcile-against-reality (flagged inline):** W2 worker task-module resolution (`backend/tasks.py` canonical + `worker/tasks.py` re-export vs `celery -A tasks` with PYTHONPATH) — the implementer picks the clean option; the compose worker uses `celery -A tasks worker` with the backend dir as WORKDIR. The fresh-import test pattern (reload after setting `MT_DATABASE_URL`) is required because `db.py` binds the engine at import.
```
