# module_template — minder-python-sdk showcase

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
- **Agent surface v3 (risk gate + events + UI driving)** — the Products tab:
  `create_product` / `delete_product` (gated) / `restock_product` / `list_products`
  (typed read) / `assist_add_product` (drives the real form via UI intents).
- **Reversibility escape route (`undo`)** — `create_product` / `update_price` /
  the `add_product` form declare *how* to reverse; it rides every decision packet.
- **Operational Graph (`@conn.graph`)** — `product_graph` in `app.py` +
  `products.graph()`; served at `/connector/graph`, shown in the **Graph** tab.
- **Agent Presence Layer (ghost cursor)** — `<AgentPresence>` in
  `frontend/src/dashboard.tsx`: narrates committed actions and parks at the
  Add-Product **Confirm** button (`data-minder-approve`) for high-risk proposals.
- **Declarative agent UI (`Agent.*`)** — every panel in `frontend/src/panels/*`
  (ProductsPanel, JobsPanel, MediaPanel, DataPanel, MetricsPanel, GraphPanel) is
  wrapped so the agent can read on-screen data and trigger actions; mounted via
  `<AgentRegistryProvider>` in `frontend/src/dashboard.tsx`.
- **Declarative agent context (`@conn.context.*`)** — the context block in
  `backend/app.py`: live `context.state("inventory")` / `context.state("jobs")`,
  `context.knowledge(...)` guardrails, and `context.note(...)` per page.

## Declarative agent layers

Two mirrored SDK layers let the agent understand and drive this module without
bespoke glue. The frontend layer reads/acts on the live UI; the backend layer
declares state, knowledge, and notes. Together they give the agent a coherent
picture of what's on screen *and* what the module knows.

### Frontend — `Agent.*` (from `minder-ui-sdk`)

Transparent wrapper components that expose on-screen data and actions:

- `<Agent.Page name description>` — declares which page/area the agent is looking
  at; child names are scoped by it (e.g. `products.add`).
- `<Agent.Data name description value>` — exposes a component's live data for the
  agent to **read** (value capped at 32768 chars, with a `truncated` flag).
- `<Agent.Button name description onAct>` — exposes an action; when the agent
  invokes it, `onAct` runs **immediately** (no approval gate).

Everything mounts under `<AgentRegistryProvider>` (already in `dashboard.tsx`,
inside `AgentDriverProvider`). A debounced snapshot is pushed to
`POST /connector/ui/snapshot` and surfaced to the agent in `GET /connector/context`
under `ui_snapshot`. The agent acts by emitting a `{intent:'act', name}` UI intent
on the existing bus. Every panel in `frontend/src/panels/` is wrapped — ProductsPanel
carries Page + Data + Button; the rest declare Page + Data. See
`docs/superpowers/specs/2026-07-13-agent-declarative-ui-wrapper-design.md`.

### Backend — `@conn.context.*` (from `minder_python_sdk`)

A decorator family to declare agent-facing context in `backend/app.py`:

- `@conn.context.state(name, description)` — decorate a fn returning **live**
  module state; evaluated on every `GET /connector/context`; may receive
  `principal` / `session_id`; fail-closed per entry; value capped at 32768 chars.
- `conn.context.knowledge(text)` — static domain knowledge / guardrail strings.
- `conn.context.note(name, text)` — static labeled area/page descriptions.
- `@conn.tool` / `@conn.read` gained `when_to_use` + `examples` kwargs for richer
  action semantics.

Static parts (knowledge, notes, tool `when_to_use` / `examples`) surface in
`GET /connector/manifest` under `context` and per-tool fields; live `state`
surfaces in `GET /connector/context` under `state[]`. This module declares
`context.state("inventory")` + `context.state("jobs")`, several
`context.knowledge(...)` guardrails, and a `context.note(...)` per page, and most
tools now carry `when_to_use` / `examples`. See
`docs/superpowers/specs/2026-07-13-agent-declarative-backend-context-design.md`.

### How the two mirror each other

The frontend declares what the agent can **see and do on the UI** (Page / Data /
Button); the backend declares what the module **is and knows** (state / knowledge /
notes). Both feed the agent through the same connector surface — `ui_snapshot` and
`state[]` on `GET /connector/context`, static context on `GET /connector/manifest` —
so the agent reasons over a single, consistent view.

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
