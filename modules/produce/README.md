# produce — MES Track A (phần mềm thuần)

Standalone Manufacturing Execution System. Human-operated; **no Minder / no AI**
(Track B SDK layers on later without touching this code). Built from
`Minder_Produce_Backlog_Roadmap` (Part 1).

## Epics → REST prefix
E11 Config `/config` · E1 Work `/work` · E2 SOP `/sop` · E3 WIP `/wip` ·
E4 Downtime `/downtime` · E5 Scrap `/scrap` · E6 OEE `/oee` · E7 Setup `/setup` ·
E8 Handover `/handover` · E9 Exception `/exception` · E10 Report `/report`.

## UI
Hybrid: 5 persona tabs (Operator / Tổ trưởng / Quản ca / Quản lý xưởng / FDE-Admin)
→ epic panels inside each. React + Vite; served standalone by the backend at `/`.

## Architecture
- Backend: FastAPI, one router per epic, `pr_*` tables on shared Postgres
  (`PR_DATABASE_URL`), lazy engine. Serves the built UI from `frontend_dist/`.
- Worker: Celery on `PR_REDIS_URL` (Redis DB `/3`) — `oee_snapshot` roll-up.
- Object store: shared MinIO (`PR_S3_*`, bucket `produce`) for defect photos
  (P-SCRAP-03); boto3 imported lazily so the app runs without it in dev.
- Data isolation: creates/owns `pr_*` tables only; never writes Minder tables.

## Run
- Local dev: backend `uvicorn app:app --port 9310` (from `backend/`), frontend
  `npm run dev` (vite on 5173, talks to 9310 via CORS).
- Docker (independent module): the core Minder stack runs on its own and does NOT
  bundle this module. First bring core up (it creates the shared `minder_net`
  network), then run this module's own compose — it joins `minder_net`, announces
  to the running Minder, and appears live:
  ```
  docker compose -f docker-compose.yml -f docker-compose.local.yml up -d   # core
  docker compose -f modules/produce/docker-compose.yml up -d --build        # module
  ```
  UI at `http://localhost:9310/`. `docker compose -f modules/produce/docker-compose.yml down`
  removes it from Minder. Set `PR_AGENT_ENABLED=0` in that compose to run Track A only.

## Test
From `backend/`: `uv run --no-sync pytest` (SQLite in-memory; no Postgres needed).

## Track B (Minder co-work)
Track B layers a Minder co-work surface (Read / Event / Command / Guidance) on top
of Track A **additively**, using `minder_python_sdk` (backend) + `minder_ui_sdk`
(frontend). It is **off by default**: set `PR_AGENT_ENABLED=1` to enable it.

- **`PR_AGENT_ENABLED`** (default `0`): when unset/falsy, `produce` runs
  byte-identically to Track A — no connector, no announce, the event seam is a
  no-op. When truthy, `app.py` builds the connector ASGI (which announces to
  Minder and runs the heartbeat) with the Track A routers + SPA attached.
- **`/connector/*` surface:** with the agent enabled the backend exposes the SDK
  connector contract at `http://localhost:9310/connector/*` — `/connector/health`,
  `/connector/manifest` (reads `read_*`, tools `cmd_*`/`guide_*`, and the module's
  event types), and `/connector/tools/{name}`. This is *in addition to* the Track A
  REST epics (`/config`, `/work`, `/sop`, …), which are unchanged.
- **Track A stays standalone when disabled:** with `PR_AGENT_ENABLED=0` there is no
  `minder_python_sdk` import, no Keycloak/announce wiring, and Track A business
  logic and human-facing behavior are untouched.

Announce env (only when the agent is enabled): `MINDER_URL`,
`MINDER_MODULE_CONNECTOR_URL`, `MINDER_MODULE_REMOTE_ENTRY`,
`MINDER_DEFAULT_AUTONOMY`, `KEYCLOAK_TOKEN_URL`, `MINDER_MODULE_CLIENT_ID`,
`MINDER_MODULE_CLIENT_SECRET`, `MINDER_MODULE_HEARTBEAT_SEC` — see
`docker-compose.yml` (`produce-web`) and `modules/module_integration.md` §4.2.
