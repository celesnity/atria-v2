---
name: monitor
description: Monitor — a read-only manufacturing fleet console over a LIVE 20-machine simulator. Fleet health at a glance (OEE / availability / throughput / quality / health streaming), per-machine drill-down analytics, and a gpt-5.4-mini Ask-AI that answers machine/fleet questions grounded in live data with the best-fit chart. Monitoring only — no actuation; the AI decision loop (measure→recommend→dispatch) lives in the Optimize module. English/Vietnamese via a lang param.
---

# monitor

**Monitor — a read-only manufacturing fleet console (Fleet · Machines · Ask AI).**

Split out of Optimize Console V2: the three *monitoring* views (Fleet, Machines, Ask AI), restyled to
the shared **Celesnity / Minder AI "two-skies"** design system (light-first; Cosmos dark / Daybreak
light) with the Guided settings-popover chrome. Self-contained vanilla `dashboard.html` — inline-SVG
charts, no React/CDN, works offline in Docker. It runs against the **live, evolving 20-machine fleet
simulator** (the IIOT fleet API) and is driven by a **real gpt-5.4-mini** brain for the Ask-AI.

## SDK connector — the agent's interface (preferred)

Monitor ships a **`minder_python_sdk` connector** (`backend/app.py`) exposing its data over the
`/connector/*` contract. **The agent should read the fleet through these connector tools**, not the
`/run` scripts:

- **`monitor_fleet`** — read the whole live fleet (every machine's state/OEE/availability/health + a
  fleet summary + the at-risk scenario). A pure read (`@conn.read`, risk none). This is the sensory
  snapshot other domains read from.
- **`monitor_machine`** (`machine_id`) — read one machine's live telemetry.
- **`monitor_ask`** (`question`, `lang?`) — a grounded, carded answer (gpt-5.4-mini). Read-only; the
  model writes prose + picks a chart intent while the numbers come from the live snapshot (it never
  invents them — `analysis.normalize_ask`).

It also provides an **Operational Graph** (`@conn.graph`: plant → line → machine → alarm) — Monitor is
the *sensory substrate* other domains query — and emits sensory **domain events**
(`machine.at_risk` / `machine.recovered`) on real transitions. It exposes **no write/actuation tool**:
Monitor is read-only, so every connector tool is risk `none` and never gated. The decision/actuation
loop lives in the Optimize module.

Run it locally with `minder-module dev monitor` (uvicorn on `:9310`); Core reaches it at
`http://127.0.0.1:9310` (static `service` block) and, once it self-registers, surfaces the three tools
to the agent. The connector reuses the same `scripts/` as the dashboard tile (one source of truth), so
both stay consistent.

Monitor is **read-only**: it observes the fleet and answers questions. It never actuates a machine.
The AI decision loop (Measure → Explain → Predict → Evaluate → Recommend → dispatch, with the
human-approval gate) lives in the **Optimize** module, not here.

## When to use

Watching a live 20-machine fleet: OEE / availability / throughput / quality / health streaming across
the plant; drilling into any one machine's analytics; and asking the AI about a machine's or the
fleet's current status and getting the best-fit chart. If you need to *act* on a problem (approve and
dispatch a recovery), that's the Optimize module.

## Dashboard (3 views)

Header keeps a **Demo / Live** toggle (defaults to **Live**) and a connection dot; language (EN/VI)
and theme (Light/Dark) live behind a settings gear popover. Light theme is the default.

1. **Fleet** — 6 KPIs, a live OEE trend (real buffered history), a 20-machine status heatmap (filter
   by state), and a run/idle/changeover/down state-mix bar. Updates every ~4 s.
2. **Machines** — per-machine analytics: metric-filtered ranked bars (availability / performance /
   quality / health), a switchable trend/loss chart (throughput / downtime / defects / FPY), and a
   runtime-vs-health scatter — all from live data.
3. **Ask AI** — a gpt-5.4-mini chat (`scripts/ai.py`) that answers about any machine's current status
   and returns tables + the best-fit chart from the 9-intent taxonomy (throughput line, cycle
   histogram, downtime Pareto, vibration/temp dual-line, state Gantt, OEE waterfall, SPC control
   chart, peer ranked-bars, temp-vs-defects scatter). The model picks the machine + intent; the
   dashboard draws the chart from **live** data, so the numbers are always real.

## Backend scripts (called via the MinderDash/AtriaDash bridge — stdin JSON → stdout JSON, always exit 0)

Monitor's backend is a trimmed, self-contained 3-script set (no decision engine, no persistence):

- `scripts/simulate.py status` — read the live fleet, map to the dashboard shape, and return a
  rolling telemetry `history`/`trends` buffer (`data/history.jsonl`) so the live time-series charts
  move. Also returns a single `scn` (fleet context) that Ask-AI passes through — but **no** ranked
  recommendation queue and **no** `actuate` command (Monitor never controls a machine).
- `scripts/ai.py ask` — `{question, machines, scn, lang?}` → `{answer, table, charts, follow_ups}` via
  gpt-5.4-mini, with a deterministic fallback on no key / network error. Numbers are never invented by
  the model — `analysis.normalize_ask` enforces that the model only writes prose and picks the machine
  + chart intent; the dashboard draws the chart from live data.
- `scripts/analysis.py` — the shared analysis layer (9-intent chart picker + the
  LLM-never-invents-numbers normaliser). Imported by `ai.py`; not a bridge entry point.

The AI reuses Minder's env config: `OPENAI_API_KEY`, `MINDER_MODEL` (gpt-5.4-mini; the pre-rebrand
`ATRIA_MODEL` still works as a deprecated fallback), `MINDER_API_BASE_URL`.

## The live fleet simulator (data source)

Built in `D:\[Research]_IIOT\[Project]_IOTMock` (`src/iiot_mcp/fleet/`): a responsive degradation
simulator serving read + control HTTP JSON. Start it:
`.venv\Scripts\python.exe scripts\run_fleet_server.py` (default `http://127.0.0.1:5050`; set
`IIOT_FLEET_SCENARIO='Progressive Machine Aging'` for a scripted decline+recovery). Override the URL
with env `IIOT_FLEET_URL` (or `?fleet=` in the dashboard). Monitor uses only the **read** endpoints
(`GET /api/fleet/snapshot`, `/summary`, `/events`) — it never calls the control endpoints.
