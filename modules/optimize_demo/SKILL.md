---
name: optimize_demo
description: Optimize Console V2 — a manufacturing fleet console + AI decision engine over a LIVE 20-machine simulator. The core agent runs the operational decision loop as SIX separate, routable skills — measure_operational_performance, explain_performance_loss, predict_operational_risk, evaluate_operational_alternatives, recommend_operational_action, replan_and_dispatch_operations — selecting the right stage per question and chaining them for compound asks. Recommend prepares a decision that a human approves before Re-plan actuates the simulator. Also exposes optimize_analyze_fleet (whole loop) and optimize_ask (targeted Q&A). English/Vietnamese via a lang param.
tools: tools.py
---

# optimize_demo

**Optimize Console V2 — a manufacturing fleet console + AI decision engine (demo).**

UI ported from the "Optimize Console V2" Claude Design (project
`73b8309d-b935-460e-816a-12b69de9435b`) on the **Celesnity / Minder AI** design system (dark-first
electric indigo). Self-contained vanilla `dashboard.html` — inline-SVG charts, no React/CDN, works
offline in Docker. It runs against a **live, evolving 20-machine fleet simulator** (the IIOT fleet
API) and is driven by a **real gpt-5.4-mini** brain for the Ask-AI and the decision narrative.

## When to use

Demonstrating live fleet monitoring + AI production-recovery decisioning: watch OEE / availability /
throughput / quality / health stream across a 20-machine fleet; ask the AI about any machine's
current status and get the best-fit chart; and on a line forecast to miss its shift target, have the
AI Measure → Explain → Predict → Evaluate → Recommend a recovery action, then **approve it to the
simulator machine** (a real control call that recovers the machine in the live views). Use the agent
tools below to read the live fleet from a chat without opening the dashboard.

## Agent tools — the 6-stage decision pipeline (this skill)

Do **not** answer an operational question with one general-purpose prompt. Select and execute the
stage skill that fits the question; for a compound ask, chain them in order. Routing:

- "What is happening / are we on target?" → **`measure_operational_performance`**
- "Why did we miss / what caused the loss?" → **`explain_performance_loss`**
- "What will happen next / will we hit target?" → **`predict_operational_risk`**
- "What are our options?" → **`evaluate_operational_alternatives`**
- "What should we do?" → **`recommend_operational_action`**
- "Apply / dispatch the decision." → **`replan_and_dispatch_operations`**

For a compound ask ("why are we behind and what should we do?"), run measure → explain → predict →
evaluate → recommend in order. **Thread the handoff**: the first stage returns `audit.execution_id`;
pass that same `execution_id` to every later stage so they all read ONE shared live snapshot and the
numbers stay coherent (target machine, gap and losses match across stages). Each stage takes an
optional `lang` (`en` default, `vi` for Vietnamese) and `fleet_url`.

Every stage returns a standard response object: `skill`, `status`, `scope`, `summary` (the prose),
`observations` / `calculations` / `findings` (each item tagged Observed / Calculated / Inferred /
Predicted / Recommended / Executed), `assumptions`, `constraints`, `recommended_next_skill`,
`data_quality` (completeness, latest_timestamp, warnings) and `confidence` (level, score,
explanation), `sources`, and `audit`. Confidence and data-quality are computed by code from the live
signals — never invented by the model, which only writes `summary`.

**Approval-required execution (safety).** `recommend_operational_action` NEVER actuates: it prepares
a decision packet persisted with status `awaiting_approval`. A human approves it (the dashboard
"Approve", or `scripts/optimize.py approve`) before `replan_and_dispatch_operations` will dispatch
and actuate the machine — that stage refuses to actuate an unapproved decision and returns
`awaiting_approval` instead.

Convenience tools:

- **`optimize_analyze_fleet(lang?, fleet_url?)`** — run the whole loop (Measure → Recommend) over one
  snapshot in a single call; stops before actuation.
- **`optimize_ask(question, fleet_url?)`** — targeted Q&A about a machine/the fleet with a best-fit
  chart suggestion.

All reuse Minder's configured model (gpt-5.4-mini via `ctx.llm_chat`) for the prose and fall back to
deterministic sentences if the model or simulator is unavailable. They require the fleet server
running (below).

Honest data sources: the only system of record is the live IIOT fleet simulator (`/api/fleet/*`) plus
the decision store (`data/*.json`). The professional roles named per stage (Production Performance
Analyst, Reliability Engineer, Operations Research Analyst, …) are analogies; each response's
`sources[]` lists the real endpoints queried.

## The live fleet simulator (data source)

Built in `D:\[Research]_IIOT\[Project]_IOTMock` (`src/iiot_mcp/fleet/`): a responsive
degradation simulator serving read + control HTTP JSON. Start it:
`.venv\Scripts\python.exe scripts\run_fleet_server.py` (default `http://127.0.0.1:5050`; set
`IIOT_FLEET_SCENARIO='Progressive Machine Aging'` for a scripted decline+recovery). Override the URL
with env `IIOT_FLEET_URL` (or `?fleet=` in the dashboard).

- Read: `GET /api/fleet/snapshot` (20 machines: live + baseline + diff), `/summary`, `/events`.
- Control (used by Approve): `POST /api/fleet/machines/<id>/{maintenance,resolve-fault,inject-fault}`,
  `/api/fleet/control/{start,pause,resume,step,speed,reset}`.

## Dashboard (4 views)

Header has a **Demo / Live** toggle (defaults to **Live**) and a **☀/☾** theme toggle.

1. **Fleet** — 6 KPIs, a live OEE trend (real buffered history), a 20-machine status heatmap
   (filter by state), and a run/idle/changeover/down state-mix bar. Updates every ~4 s.
2. **Recommendation** — the AI decision loop for the at-risk line: scenario metrics, an **AI decision
   narrative** (gpt-5.4-mini Measure→Recommend, grounded in `simulate.build_scn` numbers), the
   recommended-action hero, a forecast projection, a predicted-loss Pareto, a constraint-checked
   **Alternatives** table (the +8% speed option is blocked when machine health < 0.70), the rule
   engine, and the versioned **Decision object**. **Send to Move** approves the decision AND
   **actuates the target machine** on the live simulator (services it), which recovers it in the
   Fleet/Machines views on the next poll.
3. **Machines** — per-machine analytics: metric-filtered ranked bars (availability/performance/
   quality/health), a switchable trend/loss chart (throughput/downtime/defects/FPY), and a
   runtime-vs-health scatter — all from live data.
4. **Ask AI** — a gpt-5.4-mini chat (`scripts/ai.py`) that answers about any machine's current status
   and returns tables + the best-fit chart from the 9-intent taxonomy (throughput line, cycle
   histogram, downtime Pareto, vibration/temp dual-line, state Gantt, OEE waterfall, SPC control
   chart, peer ranked-bars, temp-vs-defects scatter). The model picks the machine + intent; the
   dashboard draws the chart from **live** data, so the numbers are always real.

## Backend scripts (called via the AtriaDash bridge — stdin JSON → stdout JSON, always exit 0)

- `scripts/simulate.py status` — read the live fleet, map to the dashboard shape, derive the
  recommendation `scn`, and return a rolling telemetry `history`/`trends` buffer (`data/history.jsonl`)
  so the live time-series charts move.
- `scripts/simulate.py actuate` — `{machine, action}` → POST the approved recovery to the fleet
  control endpoints (default: full service on the target machine). The approve-to-simulator loop.
- `scripts/ai.py ask` — `{question, machines, scn, lang?}` → `{answer, table, charts, follow_ups}` via
  gpt-5.4-mini (deterministic fallback on no key / error).
- `scripts/ai.py analyze` — `{machines, scn | execution_id, lang?}` → the whole loop (flat
  `measure/explain/predict/evaluate/recommend` prose + a per-stage `stages` map).
- `scripts/ai.py {measure|explain|predict|evaluate|recommend|replan}` — one stage's standard response
  object (same 6-stage `pipeline.py` the agent skills use). Pass `execution_id` to share one snapshot.
- `scripts/optimize.py {save,get,list,approve,reject,dispatch,outcome,audit}` — decision persistence
  + audit only (never re-derives the numbers). `scripts/store.py` is the JSON persistence layer.

The AI reuses Atria's env config: `OPENAI_API_KEY`, `ATRIA_MODEL` (gpt-5.4-mini), `ATRIA_API_BASE_URL`.
Numbers are never invented by the model — the live simulator (and `simulate.build_scn`) own them; the
model writes prose and picks the machine + chart intent.
