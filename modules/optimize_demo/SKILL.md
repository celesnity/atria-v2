---
name: optimize_demo
description: Optimize Console V2 — a manufacturing fleet console + AI decision engine over a LIVE 20-machine simulator. Fleet + Machines views stream live telemetry; an Ask-AI chat (gpt-5.4-mini) answers machine status and returns the right chart from real data; a decision loop Measures/Explains/Predicts/Evaluates/Recommends a production-recovery action and, on approval, actuates the simulator machine. Exposes agent tools (optimize_ask, optimize_analyze_fleet) that read the live fleet.
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

## Agent tools (this skill)

- **`optimize_ask(question, fleet_url?)`** — ask the live fleet a question (status, comparison, "why
  is M-02 degrading?"). Reads real telemetry and answers with a best-fit chart suggestion.
- **`optimize_analyze_fleet(fleet_url?)`** — run the Measure/Explain/Predict/Evaluate/Recommend loop
  over the live fleet and return a production-recovery narrative grounded in real numbers.

Both reuse Atria's configured model (gpt-5.4-mini via `ctx.llm_chat`) and fall back to deterministic
analysis if the model or the simulator is unavailable. They require the fleet server running (below).

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
- `scripts/ai.py ask` — `{question, machines, scn}` → `{answer, table, charts, follow_ups}` via
  gpt-5.4-mini (deterministic fallback on no key / error).
- `scripts/ai.py analyze` — `{machines, scn}` → `{measure, explain, predict, evaluate, recommend}`.
- `scripts/optimize.py {save,get,list,approve,reject,dispatch,outcome,audit}` — decision persistence
  + audit only (never re-derives the numbers). `scripts/store.py` is the JSON persistence layer.

The AI reuses Atria's env config: `OPENAI_API_KEY`, `ATRIA_MODEL` (gpt-5.4-mini), `ATRIA_API_BASE_URL`.
Numbers are never invented by the model — the live simulator (and `simulate.build_scn`) own them; the
model writes prose and picks the machine + chart intent.
