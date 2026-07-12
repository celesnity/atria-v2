# module_template — minder-module-sdk showcase

A runnable module that exercises every SDK capability. Copy it to bootstrap a new module.

## Feature → code

- **params_model (typed params)** — `template_typed_query` + `TemplateQuery` in `backend/app.py`.
- **card()** — `template_card`.
- **conn.block() federated block** — `template_block` + `frontend/src/ShowcaseBlock.tsx`.
- **streaming + mid-stream block event** — `template_stream`.
- **requires_auth** — `template_secure` (needs an authenticated principal).
- **MinderClient reverse-push (push/update block)** — `template_async_job` (background thread).
- **push_artifact** — `template_export`.
- **readiness_probe / health_probe / on_startup** — the lifecycle hooks in `app.py`.
- **@conn.route (generic passthrough)** — `/ping`.
- **expose_block + min_core_version** — `conn.expose_block(...)` + `Connector(min_core_version=...)`.
- **conn.invoke (in-process testing)** — `backend/tests/test_template.py`.
- **Celery background jobs** — `template_start_job` / `template_list_jobs` → `worker/tasks.py`.
- **S3/MinIO media storage** — `template_export` (multi-part) → `backend/media.py`.
- **DB read overlay** — `template_db_overview` → `backend/db.py` (read-only Minder tables + mt_* writes).
- **Dashboard panels** — Jobs / Media / Data / Metrics in `frontend/src/Dashboard.tsx`.

## Full-stack architecture

### Infrastructure reuse

The module shares the Minder Compose stack's `db` (PostgreSQL) and `redis` services rather than
running its own. It adds one dedicated service — MinIO — for object storage.

| Resource | Service | Notes |
|---|---|---|
| PostgreSQL | `db` (shared) | Module creates/owns `mt_*` tables; reads Minder tables read-only |
| Redis | `redis` (shared) | Module uses database `/2` (`MT_REDIS_URL=redis://redis:6379/2`) |
| Object store | `minio` (own) | Bucket `module-template`; accessed via `MT_S3_*` env vars |
| Celery broker | Redis `/2` | Worker subscribes on the same Redis DB as the web service |

### Services

- **`module-template-web`** — FastAPI connector + React dashboard; port 9300.
- **`module-template-worker`** — Celery worker; runs `tasks.py` from the backend code tree (WORKDIR `/app`).
- **`minio`** — S3-compatible object store; API port 9000, console port 9001.

### Dashboard panels

1. **Jobs** — lists background Celery jobs, their status and results.
2. **Media** — file upload/download browser backed by the MinIO bucket.
3. **Data** — read-only overlay of key Minder tables (agents, sessions, modules).
4. **Metrics** — live counters (job throughput, error rate, storage usage).

### New files → code map

| File | Purpose |
|---|---|
| `backend/db.py` | SQLAlchemy engine; `mt_*` table definitions; read-only Minder query helpers |
| `backend/media.py` | boto3 S3 client wrappers; presigned URLs; multi-part upload |
| `backend/tasks.py` | Celery app + task definitions (imported by `worker/`) |
| `backend/routes/jobs.py` | REST endpoints for `template_start_job` / `template_list_jobs` |
| `backend/routes/data.py` | REST endpoint for `template_db_overview` |
| `frontend/src/panels/JobsPanel.tsx` | Jobs dashboard panel |
| `frontend/src/panels/MediaPanel.tsx` | Media dashboard panel |
| `frontend/src/panels/DataPanel.tsx` | Data dashboard panel |
| `frontend/src/panels/MetricsPanel.tsx` | Metrics dashboard panel |

### ISOLATION CAVEAT — READ BEFORE WRITING ANY DATABASE CODE

> **This module reuses the `minder` PostgreSQL database.** It is allowed to create and write
> its own `mt_*`-prefixed tables. It may read Minder's own tables (agents, sessions, modules,
> etc.) in a **read-only** capacity for the Data panel overlay, and it must degrade gracefully
> when Minder's schema drifts (wrap Minder reads in try/except and return empty results rather
> than crashing).
>
> **Do NOT write to, alter, or drop any of Minder's tables from module code.** Violations
> corrupt the host application and are not recoverable without a database restore. If a feature
> requires persisting data, create a new `mt_`-prefixed table.

## Run

`minder-module dev module_template` for local iteration, or paste
`docker-compose.snippet.yml` into `docker-compose.yml` and `docker compose up -d --build module-template-web module-template-worker`.
Also add `module_template_media:` under the top-level `volumes:` key in your `docker-compose.yml`.
See `modules/module_integration.md` for the full contract + required env.
