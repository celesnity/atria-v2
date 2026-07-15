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
- Data isolation: creates/owns `pr_*` tables only; never writes Minder tables.

## Run
- Local dev: backend `uvicorn app:app --port 9310` (from `backend/`), frontend
  `npm run dev` (vite on 5173, talks to 9310 via CORS).
- Docker: paste `docker-compose.snippet.yml` into `docker-compose.yml`, then
  `docker compose up -d --build produce-web produce-worker`. UI at
  `http://localhost:9310/`.

## Test
From `backend/`: `uv run --no-sync pytest` (SQLite in-memory; no Postgres needed).
