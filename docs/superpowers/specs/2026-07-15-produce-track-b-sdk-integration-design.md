# Produce Track B — Minder SDK Integration (Co-work Layer) Design

**Status:** approved design, pre-plan
**Scope:** MVP co-work subset from `Minder_Produce_Backlog_Roadmap` Part 2.
**Depends on:** Track A complete (all 11 epics, REST + services, live on :9310).

## Goal

Layer the Minder co-work surface (Read / Event / Command / Guidance) onto the
finished Produce Track A **additively** — Track B only *exposes* what Track A
already built, never changes Part 1 logic or behavior. Uses `minder_python_sdk`
(backend `Connector`) and `minder_ui_sdk` (frontend agent surface).

## Non-goals

- No high-risk Commands (C05 hold lot, C08 reschedule) — deferred until the gate
  matures, per the PDF ("ranh giới kỷ luật, không phải mốc thời gian").
- No change to Track A REST, services' business logic, or human-facing UX when the
  agent layer is disabled.

## Scope — MVP co-work subset (exactly the PDF's chosen set)

- **Read:** R01–R07 (all).
- **Event:** E01 (step start/complete), E02 (downtime open/close), E03 (andon),
  E05 (exception raised) — the core MVP events.
- **Guidance:** G01 (next-step / setup suggestion for operator), G03 (decision
  packet for the shift supervisor to approve).
- **Command:** C03 (create exception + notify), C07 (auto-summarized handover
  draft), C09 (update production record) — all low-risk (Gate Thấp).

## Architecture — additive, in-process, one container

```
modules/produce/backend/
  events.py            # NEW SEAM: emit(kind, payload) + subscribe(listener); no-op by default
  domain/*/service.py  # +1 line per relevant write: events.emit("<kind>", payload) after commit
  agent/               # TRACK B — all new; nothing in Track A imports this package
    connector.py       # Connector("produce", default_autonomy, min_core_version); event sink
    reads.py           # @conn.read R01..R07  -> Track A service calls (in-process, read-only)
    events.py          # @conn.event specs + events.subscribe(-> conn.emit_event)
    commands.py        # @conn.tool C03/C07/C09 (gate + reversibility + assumption ledger)
    guidance.py        # @conn.context.state/knowledge/note + decision_packet builders
  app.py               # +1 line: app.mount("/connector", conn.app) when PR_AGENT_ENABLED
```

- **Flow:** Minder Core -> `/connector/*` (Read/Command/Event/Guidance) -> in-process
  calls into `domain/*/service`. The human operator UI keeps using Track A REST
  (`/config`, `/work`, ...). Same `produce-web` container.
- **Isolation:** `agent/` only reads/calls Track A services; Track A never imports
  `agent/`. With `PR_AGENT_ENABLED=0`, produce runs byte-identically to today's
  Track A (no `/connector` mount, seam has no listeners).
- **Deploy delta:** `produce-web` gains announce/reverse-push env (mirrors
  module_template): `MINDER_URL`, `MINDER_MODULE_CONNECTOR_URL`,
  `MINDER_MODULE_REMOTE_ENTRY`, Keycloak client id/secret, `MINDER_DEFAULT_AUTONOMY`.
  Needed for the event sink + Guidance/decision-packet reverse-push to reach Minder.

## Read mapping (`@conn.read`, typed, read-only, L1/Gate Thấp)

- R01 queue/task status -> `work.operator_queue`, `work.team_board`
- R02 WIP/station/batch -> `wip.wip_by_station`, `wip.lot_progress`, `wip.get_station_status`
- R03 shift OEE + 3 losses -> `oee.shift_oee`, `oee.loss_breakdown`
- R04 open downtime + reason history -> `downtime.open_downtimes`, `downtime.reason_library`
- R05 SOP/steps/version for a task -> `sop.released_version`
- R06 open exceptions + escalation -> `exception.open_exceptions`, `exception.escalated_exceptions`
- R07 shift handover + carry-forward -> `handover.read_handover`

## Event mapping (seam -> `conn.emit_event`, envelope to event log)

Stable kinds emitted from Track A writes via `events.emit`:
- E01: `job.started` (`wip.start_job`), `job.completed` (`wip.complete_job`),
  `step.confirmed` (`sop.confirm_step`)
- E02: `downtime.opened` (`downtime.open_downtime`), `downtime.closed` (`downtime.close_downtime`)
- E03: `andon.raised` (`downtime.raise_andon`)
- E05: `exception.raised` (`exception.raise_exception`)

`agent/events.py` registers `events.subscribe(fn)` where `fn` maps kind+payload to
`conn.emit_event(kind, payload)`; the connector's event sink is
`MinderClient.emit_event`, so envelopes land in Minder's event log. Listener errors
are caught in the seam and never break a human-initiated write.

## Command mapping (`@conn.tool` + gate; each carries reversibility + assumption ledger)

- **C03** create exception + notify supervisor — E9, Autonomy L4, Gate **Thấp** ->
  `exception.raise_exception` (+ `escalate`). Runs automatically, notifies.
  Undo: resolve/close the created exception.
- **C07** auto-summarized end-of-shift handover draft — E8, L5, Gate **Thấp** ->
  `report.end_of_shift_report` aggregation -> `handover.create_handover` (draft).
  Undo: delete the draft handover.
- **C09** update production record — E3, L5, Gate **Thấp** ->
  `wip.record_count` / `wip.set_station_status`. Undo: inverse count / prior status.

All three are low-risk so the gate lets them run without human approval, but each
still emits an event envelope and rides an assumption ledger. Gate classification
is enforced at the SDK boundary (`default_autonomy` + per-tool autonomy) before any
Track A call.

## Guidance mapping (`@conn.context` + `decision_packet` + frontend agent surface)

- **G01** next-step / correct-setup suggestion for the operator — E2, L2, Gate Thấp:
  `conn.context.state("current_job")` / `state("released_sop")` feed a
  `<GuidanceBanner>` on the Operator SOP/WIP panels; rendered directly (person still
  decides).
- **G03** decision packet for the shift supervisor to approve — E4/E9, L4, Gate TB:
  Minder pushes a `decision_packet` (with assumption ledger) rendered by the ui-sdk
  `<DecisionPacket>` on the Supervisor screen; on approve, the frontend emits a UI
  intent that invokes the mapped Command (C03/C07/C09) through the gate to the
  backend.

Panels wrap in `Agent.Page` / `Agent.Data` so the agent can **read** on-screen data
(read-only); `Agent.Button` appears only where acting is allowed.

## Frontend gating (keep Track A pure when disabled)

- `main.tsx` (standalone SPA): `agentEnabled = false` -> no agent providers mounted
  -> operator UI identical to today.
- Embedded in the Minder host: `agentEnabled = true` -> `dashboard.tsx` wraps
  `AgentDriverProvider` + `AgentRegistryProvider` (apiBase `/connector`) and adds
  `useModuleEvents` for the live stream + the G01/G03 surfaces.

## Testing

- **Unit (in-process, no Minder):** SQLite-monkeypatch fixture + `uv run --no-sync pytest`.
  - Reads: `conn.invoke("read_*")` for R01–R07, assert data matches Track A services.
  - Event seam: subscribe a test listener, call a Track A write, assert `(kind, payload)`;
    and assert **no listener -> no-op** (write still succeeds — Track A invariant).
  - Commands: `conn.invoke` C03/C07/C09 -> assert state changed + event emitted +
    decision packet has assumptions + declares undo; Gate Thấp -> runs unattended.
  - Regression with `PR_AGENT_ENABLED=0`: all existing Track A tests stay green; no
    `/connector` mount.
- **Frontend:** `npm run build` green; `agentEnabled=false` renders Track A as today;
  `agentEnabled=true` mounts agent providers + DecisionPacket.
- **Real e2e (CLAUDE.md mandate, `OPENAI_API_KEY`):** bring up Minder core +
  `produce-web` (agent enabled) in Docker, announce, run one full co-work loop —
  agent reads shift OEE -> surfaces a G03 decision packet -> supervisor approves ->
  Command executes -> envelope in the event log; confirm G01 banner + G03 packet render.

## Open questions / follow-ups (out of this spec)

- High-risk Commands C05/C08 (separate later spec once the gate matures + measurement).
- Guidance G02/G04/G05/G06 (smart poka-yoke, why-late explain, load-balance
  suggestion, downtime-reason suggestion) — next Guidance wave.
- Events E04/E06/E07 (scrap, OEE-threshold, shift-change) — next Event wave.
