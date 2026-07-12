# module_template — Full-Stack Production-Shaped Reference — Design

**Date:** 2026-07-11
**Status:** Approved (design), pending implementation plan
**Builds on:** the SDK Integration Enhancements branch. This UPGRADES the existing
`modules/module_template/` (the lightweight SDK-surface showcase) into a full-stack,
production-shaped reference module: a Celery worker, a shared-Postgres data layer,
an S3/MinIO media store, and an advanced multi-panel frontend — all reusing the
existing infra and wired through the SDK we built.

## Goal

Turn `module_template` into the canonical "real module" reference: it keeps every SDK
capability it already demos, and adds a realistic backend system — background jobs
(Celery over the shared Redis), a data layer on the shared Postgres, media in
S3/MinIO, and a four-panel advanced dashboard — so a team copying it gets a working
production shape, not a toy.

## Decisions (from brainstorming)

1. **Upgrade `module_template` in place** (do not keep a separate light version).
2. **Reuse the existing infra INSTANCES, isolate the module's DATA:**
   - **Postgres:** connect to the SAME `minder` database (`postgresql://minder:minder@db:5432/minder`).
     The module **owns** its tables `mt_jobs` and `mt_media` (Alembic-managed) for all
     WRITES; it **reads** Minder's own tables (`conversations`, `artifacts`) read-only for
     display/metrics. It never writes Minder's tables (avoids FK/enum/migration-drift
     footguns).
   - **Redis:** reuse the `redis` instance but a **separate DB index** (`redis://redis:6379/2`)
     for the Celery broker + result backend (Minder uses `/0`).
   - **S3:** a MinIO service (new) with the module's own bucket `module-template`.
3. **Advanced frontend:** all four panels — realtime job dashboard, media gallery + upload,
   data-table CRUD, and charts/metrics.

## Non-goals

- Writing Minder's own tables from the module (explicitly rejected — read-only on core tables).
- Sharing Minder's Redis DB index or SQLAlchemy models (the module has its own engine + models).
- Replacing Minder's TaskIQ substrate (the module brings Celery for itself; it reuses only the Redis instance).
- MCP (separate track).

## The isolation caveat (documented in README + spec)

Reusing the `minder` database couples the module's read models to Minder's schema. The
module reads core tables via explicit `SELECT` (SQLAlchemy `text()` with named columns),
NOT via Minder's ORM, and treats those reads as best-effort/read-only — if a read fails
(schema drift), the panel degrades gracefully. All module writes go to `mt_*` tables the
module owns. This is the safe interpretation of "same database as other services."

## Architecture

```
modules/module_template/
  backend/
    app.py            SDK connector — tools enqueue Celery jobs, CRUD mt_* rows, upload media,
                      read Minder conversations/artifacts, + the existing SDK-feature tools.
    db.py             SQLAlchemy engine (MT_DATABASE_URL → minder DB) + mt_jobs/mt_media models
                      + read helpers for Minder tables (text() SELECTs).
    media.py          boto3 S3 client (MinIO) — ensure_bucket, put_object, presigned_url.
    celery_app.py     Celery app (broker/backend = redis://redis:6379/2); send_task helpers.
    service.py        pure domain helpers (kept from the light version).
    requirements.txt  celery[redis], sqlalchemy, psycopg2-binary, boto3, alembic (module's own deps).
    alembic/          migrations creating mt_jobs, mt_media in the minder DB.
    Dockerfile        multi-stage build (frontend → slim python), installs the SDK.
    tests/            conn.invoke + db/media unit tests (fakes; no live infra).
  worker/
    tasks.py          Celery tasks: process a job → update mt_jobs rows → reverse-push a live
                      progress block via MinderClient → push_artifact on completion.
    Dockerfile / entry: `celery -A celery_app worker`.
  frontend/           MF remote — 4 panels + the ShowcaseBlock (kept).
  SKILL.md, manifest.json, icon.svg, docker-compose.snippet.yml, README.md
```

New compose services: `minio` (S3), `module-template-web` (uvicorn), `module-template-worker`
(celery). All join the `minder` network and reuse `db` + `redis`.

## Components

### 1. Data layer (`backend/db.py` + `alembic/`)

- SQLAlchemy 2.x sync engine from `MT_DATABASE_URL` (default `postgresql://minder:minder@db:5432/minder`).
- Models (module-owned): `MtJob(id, kind, status, pct, params_json, result_json, created_at, updated_at)`,
  `MtMedia(id, filename, s3_key, content_type, size, created_at)`.
- Alembic migration `0001_init` creates only `mt_jobs` + `mt_media` (never touches Minder tables).
- Read helpers (read-only on Minder tables, via `text()`): `list_conversations(limit)`,
  `count_artifacts()`, `recent_artifacts(limit)` — each wrapped in try/except returning `[]`/`0`
  on error so a schema mismatch degrades gracefully.
- Session helper `db_session()` (contextmanager). Worker + web both import this module.

### 2. Celery worker (`backend/celery_app.py` + `worker/tasks.py`)

- `celery_app = Celery("module_template", broker=$MT_REDIS_URL, backend=$MT_REDIS_URL)`,
  `MT_REDIS_URL` default `redis://redis:6379/2`.
- Task `run_job(job_id, session_id, steps)`: loads the `MtJob`, marks `running`, loops steps
  (update `pct` in DB + `MinderClient().update_block(...)` for a live progress block), marks
  `done`, writes a small report to S3 + `MinderClient().push_artifact(session_id, ...)`.
- Reverse-push uses `minder_module_sdk` (`MinderClient`) — the worker imports the SDK, never `minder`.
- A failed task marks the `MtJob` `error` and best-effort updates the block; never crashes the worker.

### 3. Media store (`backend/media.py`)

- boto3 client to `MT_S3_ENDPOINT` (MinIO, default `http://minio:9000`), creds from env,
  bucket `MT_S3_BUCKET` (default `module-template`). `ensure_bucket()` on startup (`@conn.on_startup`).
- `put_media(filename, data, content_type) -> MtMedia` (writes S3 + an `mt_media` row).
- `presigned_url(s3_key) -> str`.

### 4. Backend tools + routes (`backend/app.py`)

Keep the existing SDK-feature tools (`template_typed_query/card/block/stream/secure/async_job/export`).
Add real ones:
- `template_start_job(kind, steps, session_id)` — inserts an `MtJob`, enqueues `run_job.delay(...)`,
  returns the job id + an ack (the block updates live from the worker).
- `template_list_jobs()` — returns recent `mt_jobs` rows (for the agent + the dashboard).
- `template_db_overview()` — returns module counts (`mt_jobs`, `mt_media`) + read-only Minder
  aggregates (`conversations` count, recent `artifacts`) — demonstrates the shared-DB read.
- Dashboard routes via `@conn.route`: `/jobs` (list), `/jobs/{id}` (one), `/media` (list + presigned),
  `/media/upload` (multipart → S3 + `mt_media`), `/overview` (counts + Minder reads), `/metrics`
  (aggregates for charts). All read-checked; writes only to `mt_*`.
- Readiness probe checks DB connect + Redis ping + S3 bucket + Celery `control.ping()` — the
  module's tools stay hidden until DB/Redis/S3/worker are all reachable.

### 5. Frontend (4 panels + ShowcaseBlock)

A tabbed dashboard (`DashboardApp.tsx`) with four panels + the kept `ShowcaseBlock`:
- **Jobs** — live table of `mt_jobs` (poll `/connector/jobs`), start-job button, per-row progress.
- **Media** — upload (multipart to `/connector/media/upload`) + gallery (presigned URLs from `/connector/media`).
- **Data** — table of module rows + read-only Minder conversations (`/connector/overview`), with
  create/delete of `mt_*` demo rows.
- **Metrics** — charts (job throughput, media storage) from `/connector/metrics` (a lightweight
  SVG/canvas chart or a tiny chart lib already in web-ui; keep deps minimal).
Panels talk to `apiBase` (the connector) directly; the `ShowcaseBlock` remains the federated
chat block the SDK tools push.

### 6. Deploy (`docker-compose.snippet.yml`)

- `minio` (S3, console + api ports, a `module_template_media` volume).
- `module-template-web` (uvicorn `app:app`, port 9300, announce env + DB/Redis/S3 env + Keycloak
  `module-push` creds).
- `module-template-worker` (`celery -A celery_app worker`, same DB/Redis/S3 env, no announce).
- A one-shot / entrypoint step runs `alembic upgrade head` before the web/worker start.

## Error handling

- Every Minder-table read is try/except → degrade (empty/zero), never 500.
- Celery task failures mark the job `error` + best-effort block update; the worker keeps running.
- Media upload validates size (cap, e.g. 25 MB) → 413; bad content → 400.
- Readiness `False` while any of DB/Redis/S3/worker is unreachable → tools stay out of the catalog.
- Fail-closed SDK behavior (params_model/requires_auth) unchanged.
- The module never imports `minder`; `MinderClient`/boto3/SQLAlchemy/Celery are its own deps.

## Testing

- Unit (module `backend/tests/`, no live infra): `db.py` model round-trips against SQLite or a
  fake; `media.py` against a boto3 stub; the SDK-feature tools via `conn.invoke`; job-enqueue path
  with Celery in eager mode (`task_always_eager=True`); the readiness probe with monkeypatched
  probes. Minder-table reads tested against a stub returning rows + against a raising stub
  (degrade path).
- Frontend: build check (`npm run build`) producing the remote; a Vitest smoke test for a panel
  if a test harness is present.
- E2E (deferred to user, per CLAUDE.md, needs the compose stack + `OPENAI_API_KEY`): bring up
  `minio` + `module-template-web` + `module-template-worker`, ask the agent to start a job (watch
  the live progress block + the artifact), upload media (see it in the gallery + as an artifact),
  and view the data/metrics panels (including the read-only Minder conversation/artifact counts).

## Scope note

This is a large, multi-subsystem module. The implementation plan will phase it: **data layer →
media → celery/worker → backend tools/routes → readiness → frontend panels → deploy/compose →
docs**. Each phase is independently testable; the SDK-feature tools already work, so the module
stays runnable throughout.
