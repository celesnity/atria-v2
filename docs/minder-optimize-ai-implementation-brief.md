# Minder AI: SDK, Architecture, Produce Pattern, and Optimize Module Backlog

Status: AI implementation brief and proposed Optimize product backlog  
Prepared from the three source PDFs listed below  
Date: 2026-07-15

## 0. How to use this document

This file is intended to be the first context document given to an AI engineer working on the Optimize module.

Content is labeled as one of:

- **Source requirement**: directly summarized from the supplied Minder architecture, SDK, or Produce backlog documents.
- **Derived constraint**: a necessary implication of the source architecture.
- **Proposed Optimize design**: a recommended backlog or implementation decision that still needs product approval.

Rules for an implementing AI:

1. Preserve all source requirements and derived constraints.
2. Treat the Optimize backlog as a proposal until approved by the product owner.
3. Do not invent direct access from Minder Core to module internals. All Core interaction must pass through the SDK contract.
4. Keep Optimize useful as standalone software before adding AI control.
5. Keep operational facts in the first-party event log and Operational Graph. Optimize owns analyses, scenarios, recommendations, experiments, and measured outcomes.
6. Do not let Optimize silently change schedules, machine settings, quality holds, safety constraints, or production records.
7. Record assumptions, evidence, confidence, approvals, and outcomes for every recommendation or action.

## 1. Source documents

| Document | Role in this brief |
|---|---|
| `minder-sdk-module-engineer-en.pdf`, v1.2 | Defines how independent modules connect to Minder Core through the Python and React SDKs. |
| `Minder AI Architecture - Masterplan (1).pdf` | Defines the event-log-first architecture, Operational Graph, capability domains, autonomy ladder, and strategic sequencing. |
| `Minder_Produce_Backlog_Roadmap (2).pdf` | Provides the reference format for a module backlog: standalone product epics, separate SDK touchpoints, risk gates, dependencies, MVP, and build tracks. |

## 2. System thesis and architectural invariants

### 2.1 Product thesis - source requirement

Minder AI is an AI-native operating layer for industrial operations. It should generate and own first-party operational ground truth rather than act only as a copilot over fragmented legacy systems.

The core chain is:

```text
FIRST-PARTY EVENT LOG
        -> OPERATIONAL GRAPH
        -> AI REASONING AND AGENTS
        -> CAPABILITY MODULES
        -> CONTROLLED HUMAN/AI ACTION
        -> NEW FIRST-PARTY EVENTS
```

Legacy systems are adapters. They can seed, enrich, synchronize, or receive controlled write-back, but they are not the primary operational reality.

### 2.2 One world model - source requirement

All modules are lenses over one Operational Graph, not isolated AI products or separate truth stores.

The capability domains are:

- PLAN: decide ahead.
- PRODUCE: execute shop-floor work.
- MOVE: move materials, WIP, tools, and finished goods.
- MAINTAIN: keep assets available and reliable.
- INSPECT: ensure quality and release.
- MONITOR: sense the operation in real time; it is the sensory substrate for every domain.
- PROTECT: enforce safety and compliance constraints.
- OPTIMIZE: continuously re-decide and improve.

The main operational loop is:

```text
PLAN -> PRODUCE / MOVE / INSPECT / MAINTAIN -> OPTIMIZE -> PLAN
                       ^                         ^
                       |                         |
                    MONITOR ---------------------+

PROTECT constrains recommendations and actions across the loop.
```

### 2.3 Strategic sequence - source requirement

1. Own PRODUCE and MOVE to capture first-party work and item-flow events.
2. Add MONITOR to connect human work and item movement to machine reality.
3. Add MAINTAIN and INSPECT to connect failure and quality outcomes to operating conditions.
4. Add PLAN and OPTIMIZE after sufficient execution truth exists.
5. Add PROTECT as a live control layer.

Derived implication: Optimize must not be built as a dashboard over synthetic or poorly governed data. Its value depends on stable event semantics, entity identity, time alignment, and graph relationships from upstream domains.

## 3. Module and SDK operating model

### 3.1 Module boundary - source requirement

A Minder module is a self-contained service with its own backend, frontend, and container. It never imports host code. Communication with Minder Core is over HTTP or SSE through two SDKs:

- `minder_python_sdk`: backend connector, tools, reads, context, events, graph provider, autonomy gates, and reverse-push.
- `minder_ui_sdk`: React dashboard, observable snapshots, agent intents, decision surfaces, and agent-presence UI.

The module should normally include:

```text
optimize-web
  - Python backend connector and business API
  - React dashboard exposed through Module Federation
  - manifest.json

optimize-worker
  - background analysis, forecasting, simulation, and reverse-push jobs

module data services
  - relational store for configuration and workflow state
  - object storage for artifacts if needed
  - queue/cache for background jobs if needed
```

### 3.2 The two flows - source requirement

**Observe: module -> agent**

- Frontend sends snapshots describing the current page, visible data, and available actions.
- Backend exposes live state, knowledge, notes, and graph context.
- Backend emits events with actor and session identity.

**Steer: agent -> module**

- Agent calls typed backend tools.
- Agent sends typed UI intents such as `navigate`, `fill`, `focus`, `request_confirm`, `submit`, and `act`.
- Risky tools stop at the autonomy gate and return a decision packet instead of running.

The agent operates on declarations. It must not scrape or manipulate the DOM as its control contract.

### 3.3 Backend SDK contract - source requirement

Use one `Connector` as the module entry point. It generates the ASGI surface and collects tools, state, events, health checks, pages, forms, and controls.

Tool requirements:

- Use `@conn.read` for read-only operations. Risk is forced to `none`; reads are not gated.
- Use `@conn.tool` for actions.
- Prefer inferred input schemas from typed handler signatures or explicit Pydantic models.
- Use typed `Response[T]` results where practical.
- Use `Secret` or `OAuth2Secret` for managed credentials. Secrets must stay out of the agent-facing schema and fail closed when absent.
- Declare `risk`, `reversible`, and `undo` on every write action.
- Use structured `ToolError`, `ActionError`, or `ServiceUnavailable`; do not return unhandled 500s for known failures.
- Use streaming tools for long analyses and simulations.
- Emit domain events for meaningful state changes. The SDK also emits `action.invoked`, `action.completed`, or `action.failed` automatically.
- Preserve `event_id`, timestamp, actor, and `session_id` in event envelopes.
- Use reverse-push for background progress and results in an open session.

Tool-call processing order:

```text
validate parameters
-> authenticate
-> check idempotency
-> emit action.invoked
-> handle dry-run
-> enforce autonomy gate
-> run handler or return decision packet
-> normalize result
-> emit action.completed or action.failed
```

### 3.4 Risk and autonomy - source requirement

Autonomy ladder:

| Level | Name | Typical behavior |
|---|---|---|
| L1 | Knowledge | Answer from operational data. |
| L2 | Assistant | Guide users through work. |
| L3 | Analyst | Detect patterns and recommend action. |
| L4 | Coordinator | Orchestrate people and workflows. |
| L5 | Autonomous Operator | Execute approved actions within strict guardrails. |

SDK risk ladder:

`none < low < medium < high < critical`

A tool runs automatically only when tool risk does not exceed caller autonomy. Otherwise the SDK returns a decision packet. Industrial interpretation from the architecture:

| Risk | Example | Required treatment |
|---|---|---|
| Low | Generate an analysis or summary | May execute automatically. |
| Medium | Create an improvement task or maintenance request | Review or notification, according to policy. |
| High | Change a production schedule or place a lot on hold | Human approval required. |
| Critical | Change a machine setpoint | Restricted or human-only unless a separately approved safety architecture exists. |

### 3.5 Frontend SDK contract - source requirement

- Define the dashboard with `defineDashboard` and expose it through Module Federation.
- Keep tabs synchronized with `manifest.json`.
- Use theme tokens instead of hard-coded colors.
- Wrap observable areas with `Agent.Page`.
- Expose visible values with `Agent.Data` and executable UI actions with `Agent.Button`.
- Bind forms with `useAgentForm` inside `AgentDriverProvider`.
- Use `AgentRegistryProvider` so the UI can send full snapshots and RFC 6902 deltas.
- Use `DecisionPacket` and `useDecision` for approve, modify, and reject flows.
- Use `useModuleEvents` for the merged event stream and `useAgentContext` for autonomy and allowed actions.
- Mark fields and controls with the SDK data attributes needed by intents and agent-presence rendering.
- Treat agent presence as narration only, never as the action mechanism.

### 3.6 Core connector endpoints - source requirement

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Readiness and capability status. |
| GET | `/manifest` | Tools, input/output schemas, events, UI surface, and remote entry. |
| GET | `/context` | Autonomy, principal, live state, and allowed actions. |
| GET | `/stream` | Merged module events and UI intents, filtered by session. |
| POST | `/ui/snapshot` | Full UI snapshot or JSON-Patch delta. |
| GET/POST | `/graph` | Linked operational context. |
| POST | `/decision` | Approve, modify, or reject a decision packet. |
| POST | `/tools/{name}` | Invoke a tool. |
| POST | `/tools/{name}/stream` | Invoke a streaming tool. |

## 4. Produce backlog pattern to reuse

### 4.1 The two-track rule - source requirement

Produce separates two build tracks:

- **Track A - standalone module software**: humans can use it without Minder AI. It owns business logic, state, UI, and the first-party events it generates.
- **Track B - SDK integration**: reads, event subscriptions, commands, and UI guidance that expose only capabilities already implemented in Track A.

Track B never edits Track A by bypassing its contracts. A complete co-work loop needs Event + Guidance + Command.

Derived Optimize rule: build the optimization workspace, KPI engine, analyses, scenarios, recommendations, and experiment tracking as Track A. Add Minder observation and steering through Track B.

### 4.2 Produce standalone epics - source summary

| Epic | Scope | Key MVP content |
|---|---|---|
| E1 Work assignment and queues | Operator and team work queues, ownership, balancing | Personal queue, accept/start task, supervisor reassignment, team status |
| E2 Guided execution and e-SOP | Versioned instructions, step confirmation, poka-yoke | Instructions, step completion, required-step/value gates, approved SOP versions |
| E3 WIP and production steps | Start/finish timestamps, counts, station status, batch progress | Job/step timing, quantities, station state |
| E4 Downtime and andon | Structured reasons, support calls, thresholds, live andon | Downtime reason, andon, team andon view |
| E5 Scrap, defects, and rework | Scrap reasons, rework routing, evidence, holds | Scrap capture and rework marking |
| E6 Cycle time and OEE data | Automatic cycle time, standards, live OEE, loss breakdown | Cycle timing, order target/ideal cycle, live OEE |
| E7 Setup and changeover | Checklists, timing, first piece, product standards | Changeover checklist and correct standard selection |
| E8 Shift handover | Outgoing summary, incoming review, carry-forward | Handover creation/read and cross-shift downtime handling |
| E9 Exceptions and escalation | Blocked jobs, classification, escalation, replenishment request | Raise and triage exceptions |
| E10 Reporting and displays | Live team dashboard, shift report, trends, causal explanation | Live team dashboard and generated end-of-shift report |
| E11 Configuration and master data | Operations, stations, parts, standards, skills, thresholds | Line/operation model and versioned master data |

### 4.3 Produce SDK pattern - source summary

Produce defines four SDK categories:

- Read/Query: server-side state reads, L1, low/no gate.
- Event subscription: backend domain events, generally L1-L3 and low gate.
- Command/Write: typed server-side actions, L3-L5, always risk classified.
- Guidance/Decision surface: UI proposals and explanations, usually L2-L3; a human decides where required.

Cross-cutting SDK obligations:

- All actions are typed function calls, not UI scraping.
- Every accepted write emits an event back to the log.
- The gate blocks at the SDK boundary before the module is changed.
- Every decision packet carries an assumption ledger.
- Core has no path into the module outside the SDK.

### 4.4 Produce dependency lesson - source summary

Produce's critical path is:

```text
E11 Config -> E1 Work -> E3 WIP/Step -> E4 Downtime -> E6 OEE -> E8 Handover
```

SDK Core waits for stable Track A APIs. Read/Event depends on SDK Core and the source epic. Guidance also depends on the Track A UI. Low-risk commands mature before high-risk commands.

Produce MVP deliberately demonstrates a safe co-work loop with core reads/events, selected guidance, and low-risk commands. High-risk commands such as holding a lot or changing a schedule wait for a mature gate and trustworthy measurement. This is a maturity boundary, not simply a calendar date.

## 5. Optimize module product definition

Everything in Sections 5 through 11 is a **proposed Optimize design** derived from the source architecture and Produce pattern.

### 5.1 Purpose

Optimize continuously improves operational decisions by turning trusted execution history and live context into:

- comparable KPI baselines;
- loss and bottleneck explanations;
- evidence-backed root-cause hypotheses;
- forecasts and early warnings;
- prioritized recommendations;
- constrained scenarios and simulations;
- improvement experiments;
- verified financial, capacity, quality, labor, and energy outcomes;
- feedback to Plan and controlled action requests to execution modules.

### 5.2 Product boundary

Optimize should own:

- KPI definitions, calculation versions, and analysis windows;
- baselines and comparison cohorts;
- saved analyses and evidence graphs;
- bottleneck and loss findings;
- predictions and model/version metadata;
- recommendations, assumptions, confidence, expected impact, and constraints;
- scenarios, simulation inputs, outputs, and sensitivity results;
- improvement opportunities, experiments, actions, owners, and measured outcomes;
- benefit validation and portfolio reporting.

Optimize should not own or silently rewrite:

- raw production, material, sensor, maintenance, quality, safety, or scheduling facts;
- source-domain master data;
- machine control or PLC setpoints;
- safety policy;
- production schedules, quality holds, or maintenance work orders without gated domain commands.

### 5.3 Personas

| Persona | Main need |
|---|---|
| Continuous Improvement Engineer | Find, test, and validate improvement opportunities. |
| Plant Manager | Prioritize the highest-value losses and track realized benefit. |
| Production Manager / Shift Manager | Understand why output missed plan and choose near-term corrective action. |
| Process Engineer | Analyze process relationships and compare parameter or routing scenarios. |
| Maintenance / Reliability Lead | Connect recurring downtime and degradation to operating context. |
| Quality Lead | Connect yield and defect losses to production, material, and process conditions. |
| Energy / Sustainability Lead | Optimize energy per good unit without violating quality or throughput constraints. |
| Planner | Consume validated capacity and cycle-time insights for replanning. |
| FDE / Admin | Configure entity mappings, KPI semantics, units, policies, thresholds, and connectors. |

### 5.4 Required upstream inputs

| Domain | Minimum useful inputs |
|---|---|
| PRODUCE | Work orders, targets, ideal cycles, counts, WIP, step timestamps, downtime, scrap/rework, changeovers, shift context, exceptions |
| MOVE | Material availability, movements, shortages, dwell time, line-side replenishment |
| MONITOR | Machine state, sensor/time-series data, alarms, process and energy signals |
| MAINTAIN | Failures, work requests/orders, asset health, interventions, parts, MTBF/MTTR context |
| INSPECT | Inspection results, defects, measurements, nonconformance, holds, genealogy |
| PLAN | Demand, production plan, sequence, capacity assumptions, labor/material constraints |
| PROTECT | Safety rules, permits, hazards, operating limits, prohibited actions |
| KNOW / Graph | Stable entity identity and relationships across all inputs |

The MVP may start with Produce data only, but it must keep interfaces ready for the other domains.

### 5.5 Core outcome loop

```text
observe trusted events and graph state
-> select a governed KPI and comparison window
-> quantify the loss
-> locate the constraint or bottleneck
-> assemble evidence and hypotheses
-> recommend or simulate options
-> human accepts, modifies, or rejects
-> create controlled actions in source modules
-> observe outcome events
-> validate realized benefit
-> update confidence and planning assumptions
```

## 6. Optimize Track A - standalone software backlog

Track A must be useful to analysts and managers without Minder Core. `[MVP]` indicates the recommended first release.

### O1. Configuration, identity, and KPI semantics

- **O-CFG-01 [MVP]** As an FDE/Admin, I want to map lines, stations, machines, products, shifts, and reason codes to stable graph IDs so that analyses join the same real-world entities.
- **O-CFG-02 [MVP]** As an FDE/Admin, I want to define KPI formulas, units, calendars, exclusions, and data-quality rules with versions so that every result is reproducible.
- **O-CFG-03 [MVP]** As a CI Engineer, I want to select an analysis window and comparison baseline so that current performance is compared fairly.
- **O-CFG-04** As an FDE/Admin, I want to configure cost, labor, energy, and carbon factors with effective dates so that benefit estimates use governed assumptions.
- **O-CFG-05** As an FDE/Admin, I want to configure action policies, risk thresholds, confidence thresholds, and protected constraints so that recommendations remain bounded.

### O2. Unified performance workspace

- **O-PERF-01 [MVP]** As a Plant Manager, I want throughput, OEE, yield, scrap, downtime, cycle time, and plan attainment in one comparable view so that I can see where performance was lost.
- **O-PERF-02 [MVP]** As a Production Manager, I want to slice performance by plant, area, line, station, product, order, shift, and time so that I can isolate the affected context.
- **O-PERF-03 [MVP]** As a CI Engineer, I want every KPI value to show formula version, source coverage, missing data, and freshness so that I know whether it is trustworthy.
- **O-PERF-04** As a Plant Manager, I want comparable cohorts such as same product, shift, line, or operating mode so that comparisons do not mix incompatible conditions.

### O3. Loss tree and bottleneck detection

- **O-LOSS-01 [MVP]** As a Production Manager, I want output loss decomposed into availability, performance, quality, changeover, starvation, blocking, and other governed categories so that the largest losses are visible.
- **O-LOSS-02 [MVP]** As a CI Engineer, I want a Pareto view of losses by reason, asset, station, product, and shift so that I can focus on the vital few.
- **O-LOSS-03 [MVP]** As a CI Engineer, I want bottleneck candidates ranked using throughput, queue/WIP, utilization, blocking, starvation, and cycle-time evidence so that a busy station is not automatically mislabeled as the constraint.
- **O-LOSS-04** As a Production Manager, I want bottleneck movement over time so that I can distinguish a persistent constraint from a transient one.
- **O-LOSS-05** As a CI Engineer, I want the system to estimate recoverable capacity for each loss category with stated assumptions so that opportunities can be compared.

### O4. Root-cause investigation and evidence

- **O-RCA-01 [MVP]** As a CI Engineer, I want to open an investigation from a KPI deviation, loss, alarm, downtime, defect, or missed plan so that context is preserved.
- **O-RCA-02 [MVP]** As a CI Engineer, I want a time-aligned evidence timeline across production, material, sensor, maintenance, quality, and shift events so that I can see what changed before the outcome.
- **O-RCA-03 [MVP]** As a CI Engineer, I want hypotheses ranked with supporting and contradicting evidence, confidence, and data gaps so that correlation is not presented as certainty.
- **O-RCA-04** As a Process Engineer, I want to compare affected runs with matched good runs so that likely differentiating conditions become visible.
- **O-RCA-05** As a CI Engineer, I want to save, review, version, and close an investigation with a human conclusion so that organizational learning is auditable.

### O5. Prediction and early warning

- **O-PRED-01** As a Production Manager, I want a forecast of end-of-shift output and plan attainment with a confidence interval so that I can intervene early.
- **O-PRED-02** As a CI Engineer, I want emerging downtime, quality, cycle-time, or energy anomalies detected against the correct operating context so that false alarms are reduced.
- **O-PRED-03** As a Reliability Lead, I want recurring patterns that precede downtime or failure identified so that maintenance can act before a repeat.
- **O-PRED-04** As an FDE/Admin, I want every prediction tied to model version, training window, feature lineage, performance metrics, and drift status so that models are governed.
- **O-PRED-05** As a manager, I want alert policies based on expected impact, confidence, persistence, and cooldown so that the team is not flooded.

### O6. Recommendation and prioritization

- **O-REC-01 [MVP]** As a CI Engineer, I want recommendations ranked by expected impact, effort, confidence, urgency, risk, and affected constraints so that I can choose what to do first.
- **O-REC-02 [MVP]** As a manager, I want each recommendation to include evidence, assumptions, expected KPI movement, side effects, required owner, and rollback/stop conditions so that approval is informed.
- **O-REC-03 [MVP]** As a manager, I want to accept, modify, reject, defer, or request more evidence and record a reason so that decisions become training and audit data.
- **O-REC-04** As a CI Engineer, I want duplicate or conflicting recommendations merged or flagged so that teams do not launch competing actions.
- **O-REC-05** As a Plant Manager, I want a ranked opportunity portfolio constrained by budget, labor, downtime window, safety, and production commitments so that prioritization is realistic.

### O7. Scenario analysis and simulation

- **O-SIM-01** As a Planner, I want to compare sequence, staffing, changeover, maintenance-window, and buffer scenarios without changing live operations so that I can evaluate trade-offs.
- **O-SIM-02** As a Process Engineer, I want simulation inputs, model assumptions, constraints, and calibration quality visible so that results are not treated as magic.
- **O-SIM-03** As a manager, I want scenarios compared across throughput, service, cost, quality, energy, WIP, and risk so that local optimization does not harm the system.
- **O-SIM-04** As a CI Engineer, I want sensitivity analysis for uncertain assumptions so that I know which inputs drive the result.
- **O-SIM-05** As a Planner, I want an approved scenario exported as a proposal to Plan, not applied directly, so that schedule governance remains intact.

### O8. Improvement experiments and benefit validation

- **O-EXP-01 [MVP]** As a CI Engineer, I want to convert an accepted recommendation into an improvement experiment with owner, hypothesis, target, scope, start/end dates, and stop conditions so that execution is disciplined.
- **O-EXP-02 [MVP]** As an owner, I want linked action tasks created in the appropriate source modules so that improvement work is executed where operational truth is recorded.
- **O-EXP-03 [MVP]** As a CI Engineer, I want pre/post results compared against a fair baseline and control for mix or schedule changes so that benefit is not overstated.
- **O-EXP-04 [MVP]** As a Plant Manager, I want benefit classified as estimated, validated, sustained, or regressed so that portfolio claims remain credible.
- **O-EXP-05** As a CI Engineer, I want successful countermeasures and failed attempts attached to the graph so that future recommendations learn from outcomes.

### O9. Cost and energy optimization

- **O-CE-01** As a Plant Manager, I want cost per good unit decomposed into time, labor, scrap, energy, material, and downtime drivers so that operational loss becomes financial impact.
- **O-CE-02** As an Energy Lead, I want energy per good unit normalized by product and operating mode so that efficiency comparisons are fair.
- **O-CE-03** As an Energy Lead, I want high baseload, peak demand, idle consumption, and energy anomalies identified so that waste is actionable.
- **O-CE-04** As a manager, I want energy or cost recommendations checked against throughput, quality, maintenance, and safety constraints so that savings do not create operational harm.

### O10. Reporting, governance, and portfolio

- **O-RPT-01 [MVP]** As a Plant Manager, I want a weekly optimization review showing top losses, active recommendations, experiment status, realized benefit, and unresolved data-quality issues so that governance is routine.
- **O-RPT-02 [MVP]** As a CI Leader, I want an opportunity funnel from detected to investigated, approved, running, validated, and sustained so that improvement work is visible.
- **O-RPT-03** As an auditor, I want a complete history of calculation versions, model versions, recommendations, approvals, actions, and outcomes so that decisions are traceable.
- **O-RPT-04** As a Plant Manager, I want cross-line and cross-site benchmarking with governed comparability rules so that best practices can be transferred safely.

## 7. Optimize Track B - SDK interaction backlog

### 7.1 Read / Query - L1 Knowledge, risk none, backend

| ID | Proposed SDK capability | Source epic | MVP |
|---|---|---|---|
| OPT-R01 | Read governed KPI values, targets, baselines, coverage, and freshness for a scope and time window. | O1, O2 | Yes |
| OPT-R02 | Read loss tree, Pareto, and bottleneck candidates with evidence. | O3 | Yes |
| OPT-R03 | Read an investigation, timeline, hypotheses, evidence, confidence, and data gaps. | O4 | Yes |
| OPT-R04 | Read ranked recommendations and current decision state. | O6 | Yes |
| OPT-R05 | Read active experiments, action status, and benefit-validation state. | O8 | Yes |
| OPT-R06 | Read forecasts, anomaly state, model version, and drift status. | O5 | Later |
| OPT-R07 | Read scenario inputs, outputs, constraints, and sensitivity. | O7 | Later |
| OPT-R08 | Read cost and energy loss breakdowns. | O9 | Later |
| OPT-R09 | Read optimization portfolio and governance audit history. | O10 | Yes |

### 7.2 Event subscription - L1 to L3, low risk, backend

Optimize consumes upstream domain events and emits its own domain events.

| ID | Event or subscription | Direction | MVP |
|---|---|---|---|
| OPT-E01 | Production step/count/WIP/downtime/scrap/changeover/exception/shift events | Consume from Produce | Yes |
| OPT-E02 | Material movement, shortage, dwell, and replenishment events | Consume from Move | Later |
| OPT-E03 | Machine state, alarm, sensor, process, and energy events | Consume from Monitor | Later |
| OPT-E04 | Failure, work order, intervention, and asset-health events | Consume from Maintain | Later |
| OPT-E05 | Inspection, defect, measurement, hold, and release events | Consume from Inspect | Later |
| OPT-E06 | Plan, schedule, target, sequence, and constraint changes | Consume from Plan | Later |
| OPT-E07 | Safety policy, permit, hazard, and operating-limit changes | Consume from Protect | Before action expansion |
| OPT-E08 | `optimization.loss_detected` and `optimization.bottleneck_changed` | Emit | Yes |
| OPT-E09 | `optimization.investigation_opened/updated/closed` | Emit | Yes |
| OPT-E10 | `optimization.recommendation_created/decided` | Emit | Yes |
| OPT-E11 | `optimization.experiment_started/completed` and `optimization.benefit_validated/regressed` | Emit | Yes |
| OPT-E12 | `optimization.forecast_updated` and `optimization.anomaly_detected/cleared` | Emit | Later |
| OPT-E13 | `optimization.scenario_completed` | Emit | Later |

### 7.3 Command / Write - typed, gated, backend

| ID | Proposed command | Autonomy | Risk | MVP |
|---|---|---:|---:|---|
| OPT-C01 | Save or refresh an analysis snapshot. | L3 | low | Yes |
| OPT-C02 | Open/update/close an investigation. | L3 | low | Yes |
| OPT-C03 | Create a recommendation draft from evidence. | L3 | low | Yes |
| OPT-C04 | Accept, modify, reject, defer, or request more evidence for a recommendation. | L3/L4 | medium | Yes |
| OPT-C05 | Create or update an improvement experiment. | L4 | medium | Yes |
| OPT-C06 | Create low-risk action tasks in Produce, Move, Maintain, or Inspect through those modules' SDK commands. | L4 | medium | After source command exists |
| OPT-C07 | Run a forecast or anomaly-analysis job. | L3 | low | Later |
| OPT-C08 | Run a read-only scenario or simulation. | L3 | low | Later |
| OPT-C09 | Submit an approved scenario to Plan as a proposal. | L4 | high | Later |
| OPT-C10 | Request a production sequence or schedule change. | L4 | high | Later |
| OPT-C11 | Request a quality hold, maintenance action, or material reroute. | L4 | high | Later |
| OPT-C12 | Apply a machine or process setpoint change. | L5 | critical | Out of scope / human-only by default |

Command rules:

- C06 and C09-C12 must call the owning module's SDK command. Optimize must not write the other module's database.
- High-risk commands require a human decision packet even if a model has high confidence.
- Critical machine/process changes remain unavailable until a separately approved control and safety architecture exists.
- Every accepted write must emit both the normal SDK action envelope and an Optimize domain event.
- All commands must support idempotency where duplicate execution could create duplicate work or decisions.

### 7.4 Guidance / Decision surface - UI

| ID | Proposed UI guidance | Autonomy | Gate | MVP |
|---|---|---:|---:|---|
| OPT-G01 | Explain the selected KPI deviation and top loss contributors. | L3 | low | Yes |
| OPT-G02 | Highlight the current bottleneck candidate and show supporting/contradicting evidence. | L3 | low | Yes |
| OPT-G03 | Guide an analyst through an investigation and focus missing evidence fields. | L2 | low | Yes |
| OPT-G04 | Surface a recommendation card with impact, confidence, assumptions, constraints, and side effects. | L3 | medium | Yes |
| OPT-G05 | Surface a decision packet for recommendation or experiment approval. | L4 | medium | Yes |
| OPT-G06 | Explain why a line missed plan by traversing the Operational Graph. | L3 | low | Yes |
| OPT-G07 | Compare scenarios and explain trade-offs and sensitivity. | L3 | medium | Later |
| OPT-G08 | Warn when data quality, model drift, or an invalid comparison makes a conclusion unreliable. | L3 | low | Yes |
| OPT-G09 | Surface high-risk cross-module action requests for human approval. | L4 | high | Later |

## 8. Optimize dependency roadmap

### 8.1 Internal dependency table

| Item | Blocked by |
|---|---|
| O1 Configuration and KPI semantics | Stable graph IDs and upstream event contracts |
| O2 Performance workspace | O1 plus Produce core event history |
| O3 Loss tree and bottlenecks | O1, O2 |
| O4 Root-cause investigation | O2, O3; richer results require Move/Monitor/Maintain/Inspect |
| O5 Prediction and warning | O1, O2, sufficient time-series history, model governance; usually O4 labels/outcomes |
| O6 Recommendations | O3, O4, action/constraint catalog |
| O7 Scenario and simulation | O1, O2, O3, calibrated model, Plan constraints |
| O8 Experiments and validation | O6, source-module action/task integration, stable outcome events |
| O9 Cost and energy | O1, O2, governed cost/energy factors, Monitor energy data |
| O10 Reporting and portfolio | O2; full value requires O6 and O8 |
| SDK-Core | Stable Optimize Track A APIs and event schemas |
| SDK Read/Event | SDK-Core plus relevant Track A epic and upstream subscriptions |
| SDK Guidance | SDK-Core, SDK Read/Event, and stable Track A UI surfaces |
| SDK low/medium-risk commands | SDK-Core plus target Track A workflow |
| SDK high-risk cross-module commands | Mature low/medium commands, mature gate and audit measurement, source-module command, and Protect constraints |

### 8.2 Proposed critical path

```text
Graph identity and event quality
-> O1 KPI semantics
-> O2 Performance workspace
-> O3 Loss and bottleneck
-> O4 Root-cause evidence
-> O6 Recommendations
-> O8 Experiment and benefit validation
```

This is the shortest path to a closed improvement loop. Prediction and simulation are valuable branches, but neither should block the first evidence -> decision -> action -> measured outcome loop.

### 8.3 External maturity gates

Optimize can advance only when the following gates are met:

1. **Identity gate**: stable IDs for plant, line, station, machine, product, order, lot, shift, and event.
2. **Time gate**: timestamps, time zones, event ordering, shift calendars, and late-event handling are defined.
3. **Semantic gate**: versioned definitions exist for counts, good/scrap, downtime, ideal cycle, target, availability, performance, quality, and OEE.
4. **Quality gate**: freshness, completeness, duplication, missing reason codes, and source coverage are measurable.
5. **Evidence gate**: every conclusion can link to source events and graph nodes.
6. **Action gate**: target modules expose typed, risk-classified, auditable commands.
7. **Safety gate**: Protect constraints and human approval exist before recommendations can become high-risk actions.
8. **Learning gate**: accepted/rejected recommendations and realized outcomes are captured before autonomy expands.

## 9. Recommended MVP

### 9.1 MVP scope

Start with a Produce-backed Optimize MVP for one plant or line:

- O1: stable mappings, KPI definitions, calculation versions, baselines, and data-quality status.
- O2: unified performance view with drill-down and provenance.
- O3: loss tree, Pareto, and evidence-based bottleneck candidates.
- O4: investigation workspace, multi-event timeline, hypotheses, evidence, and human conclusion.
- O6: ranked recommendation cards and decision workflow.
- O8: improvement experiments, linked actions, before/after validation, and benefit status.
- O10: weekly review and opportunity funnel.
- SDK: OPT-R01-R05 and R09; E01 and E08-E11; C01-C05; G01-G06, G08.

### 9.2 Explicit MVP exclusions

- No automatic schedule change.
- No lot hold or release.
- No machine/process setpoint change.
- No black-box prediction marketed as causal truth.
- No full digital twin.
- No cross-site benchmarking until comparability rules exist.
- No claimed financial benefit without governed factors and validation state.
- No recommendation without evidence, assumptions, confidence, and constraints.

### 9.3 MVP demonstration scenario

Use one end-to-end scenario:

1. Produce emits step, count, downtime, scrap, and shift events.
2. Optimize detects that Line A missed output target and quantifies the gap.
3. The loss tree shows availability loss dominated by repeated micro-stops at Station 4.
4. The evidence timeline links micro-stops to a product family, changeover context, operator notes, and prior events.
5. Minder surfaces a cautious hypothesis and explicitly shows contradicting evidence and missing sensor context.
6. Optimize proposes a low-risk investigation/checklist or maintenance-inspection task, with expected impact and stop conditions.
7. A human modifies and approves the recommendation.
8. The owning module receives the typed task through its SDK.
9. Completion events return to the event log.
10. Optimize compares a matched post-change window with the baseline and marks benefit as estimated or validated.

This demonstrates the complete Observe -> Reason -> Guide -> Approve -> Act -> Observe -> Validate loop without risky autonomous control.

## 10. Implementation blueprint for an AI engineer

### 10.1 Suggested backend domains

```text
optimize/
  connector/       # Minder SDK declarations only
  config/          # KPI, mappings, calendars, factors, policies
  ingestion/       # event subscriptions, normalization, late-event handling
  metrics/         # versioned KPI calculations and provenance
  analysis/        # loss tree, Pareto, bottleneck, cohort comparison
  investigations/  # timelines, evidence, hypotheses, conclusions
  recommendations/ # ranking, decisions, assumptions, constraints
  experiments/     # action links, baselines, outcomes, validation
  forecasting/     # later: models, registry, drift, predictions
  simulation/      # later: scenario models and calibration
  portfolio/       # reporting, benefit rollup, audit views
  graph/           # node/edge projections and traversal helpers
  workers/         # long-running analysis, forecast, simulation jobs
```

Keep business logic outside decorated connector handlers. Connector tools should validate, authorize, call application services, and normalize SDK responses.

### 10.2 Minimum entities

| Entity | Essential fields |
|---|---|
| `KpiDefinition` | id, name, version, formula, unit, scope rules, exclusions, effective time |
| `AnalysisWindow` | scope, start/end, timezone, baseline method, comparison cohort |
| `MetricResult` | KPI version, value, target, coverage, freshness, provenance refs |
| `LossItem` | category, amount, unit, recoverable estimate, evidence refs |
| `BottleneckFinding` | candidate entity, rank, method, supporting/contradicting evidence |
| `Investigation` | trigger, scope, owner, state, evidence timeline, conclusion |
| `Hypothesis` | statement, confidence, supporting refs, contradicting refs, data gaps |
| `Recommendation` | action proposal, expected impact, effort, risk, confidence, assumptions, constraints, status |
| `Decision` | verdict, actor, timestamp, modifications, reason, decision packet version |
| `Scenario` | inputs, constraints, model version, outputs, sensitivity, approval state |
| `Experiment` | hypothesis, baseline, target, owner, action links, dates, stop conditions |
| `BenefitResult` | expected/observed impact, method, confidence, status, sustained-through date |
| `ModelVersion` | purpose, training window, feature lineage, validation metrics, drift status |
| `AuditRecord` | actor, action, entity, before/after refs, session, timestamp |

All records that support decisions should be append-only or versioned. Corrections should preserve history.

### 10.3 Initial connector tool names

Use stable, verb-first names:

```text
read_kpi_summary
read_loss_tree
read_bottleneck_candidates
read_investigation
read_recommendations
read_experiments
read_optimization_portfolio

refresh_analysis
open_investigation
update_investigation
close_investigation
draft_recommendation
decide_recommendation
create_experiment
update_experiment
validate_benefit
```

Later:

```text
run_forecast
run_scenario
submit_plan_proposal
request_cross_module_action
```

### 10.4 Initial live context

Expose compact state, not raw datasets:

- `optimization_scope`: selected plant/line/shift and time window.
- `data_readiness`: freshness, coverage, late events, unresolved identity mappings.
- `top_losses`: current top loss categories and values.
- `bottleneck_summary`: top candidate and confidence.
- `open_investigations`: count and highest-priority items.
- `pending_decisions`: recommendations awaiting human action.
- `active_experiments`: current experiments and health.
- `model_health`: later, active model versions and drift warnings.

Knowledge and notes should state KPI definitions, comparison rules, UI areas, and action policies.

### 10.5 Graph provider

The Optimize graph view should connect, at minimum:

```text
KPI deviation
-> loss item
-> source event(s)
-> line/station/machine
-> product/order/lot/shift
-> downtime/defect/material/failure context
-> hypothesis
-> recommendation
-> decision
-> action task
-> outcome event(s)
-> validated benefit
```

The agent should be able to traverse this graph to answer both "why" and "what happened after we acted?"

### 10.6 Dashboard tabs

Recommended first tabs:

1. **Overview** - KPI status, data readiness, top losses, pending decisions.
2. **Losses** - loss tree, Pareto, bottleneck evidence.
3. **Investigations** - timeline, hypotheses, evidence, data gaps.
4. **Recommendations** - ranked cards and decision packets.
5. **Experiments** - action progress and benefit validation.
6. **Portfolio** - funnel, realized benefit, governance.
7. **Config** - mappings, KPI definitions, calendars, factors, policies.

Later tabs: Forecasts, Scenarios, Energy.

Every tab should declare visible data and actions with the UI SDK. Forms for recommendations, decisions, and experiments should use `useAgentForm` so the agent can prefill while the human retains control.

## 11. Optimize operational skill architecture

This section defines the AI skill layer for Optimize. The six skills behave like a coordinated professional team rather than one general-purpose chatbot.

```text
Measure
-> Explain
-> Predict
-> Evaluate alternatives
-> Recommend or act
-> Re-plan and dispatch
-> Measure again
```

Each skill has a narrow responsibility, an authorized tool set, a structured output, explicit guardrails, and a handoff to the next stage. A skill may be called independently for a narrow question, or several may run as a controlled sequence.

### 11.1 Tool-source policy for all Optimize skills

The original skill concept names MES, SCADA, WMS, CMMS, QMS, ERP, APS, historians, and workforce systems. In Minder, these are not direct model tools by default. Apply this priority:

1. Read first-party events and linked state through the Operational Graph and owning Minder modules.
2. Use typed SDK reads exposed by Produce, Move, Monitor, Maintain, Inspect, Plan, Protect, and Optimize.
3. Use module events for live or incremental changes.
4. Use a legacy adapter only when the owning module has not yet captured the required fact. The adapter must expose provenance and freshness and must not silently become the source of truth.
5. Execute changes only through the typed, gated command of the module that owns the operational state.

Authoritative routing by data type:

| Data type | Preferred Minder source | Legacy adapter if required |
|---|---|---|
| Actual production, WIP, steps, downtime, scrap | Produce | MES/MOM |
| Machine state, alarms, sensors, energy signals | Monitor | PLC/SCADA/historian |
| Production plan, target, sequence, capacity assumptions | Plan | APS/ERP |
| Material location, movement, shortage, replenishment | Move | WMS/ERP inventory |
| Failure, asset health, maintenance action | Maintain | CMMS/EAM/APM |
| Inspection, defect, hold, release, genealogy | Inspect | QMS/LIMS |
| Safety limits, permits, hazards, action restrictions | Protect | EHS/permit/LOTO system |
| Labor availability and qualification | Produce/Plan graph context | Workforce system |
| SOP and controlled instructions | Produce/KNOW | Controlled document repository |
| KPI, loss, hypothesis, recommendation, experiment | Optimize | None; Optimize owns these records |

When sources disagree, return the conflict and provenance. Never silently choose a convenient value.

### 11.2 Skill 1 - `measure_operational_performance`

**Professional role:** Production Performance Analyst / Manufacturing Data Analyst  
**Stage objective:** Quantify what is happening and the gap between actual and expected performance without assigning causes.  
**Related backlog:** O1, O2; OPT-R01; OPT-C01; OPT-G01.

Use for questions such as:

- How is Line 2 performing?
- Are we meeting the shift target?
- What changed in the last hour?
- Which line, station, job, or product is underperforming?
- How much output has been lost?

Required inputs:

- operational scope resolved to graph IDs;
- analysis period, timezone, shift calendar, and freshness requirement;
- governed KPI definition and version;
- plan/target and actual production events;
- machine or station runtime/state history.

Useful context includes ideal and actual cycle time, good/scrap/rework count, planned production time, downtime, job/product, labor, material, and energy.

Authorized tools:

| Tool | Purpose |
|---|---|
| `read_kpi_summary` | Retrieve governed KPI results, target, formula version, coverage, and freshness. |
| `refresh_analysis` | Recalculate an analysis snapshot when current values are absent or stale. |
| Produce reads | Counts, WIP, production steps, downtime, scrap, jobs, and shifts. |
| Plan reads | Planned quantity, timing, sequence, and target. |
| Monitor reads/graph | Machine state and time-series context when required by the KPI. |
| `read_loss_tree` | Read existing quantified losses only; do not interpret their cause in this stage. |

Professional procedure:

1. Resolve scope and entity IDs.
2. Retrieve the applicable KPI formula, unit, calendar, exclusions, and version.
3. Retrieve target and actual events for exactly the same window.
4. Normalize timestamps and shift boundaries.
5. detect missing, duplicated, delayed, corrected, or conflicting records.
6. Calculate or retrieve KPIs and provenance.
7. Compare actual performance with plan, standard, previous comparable period, and approved cohort where requested.
8. Identify material deviations without attributing cause.
9. Label every value as observed or calculated.

Typical calculations, only when the governed plant definition agrees:

```text
attainment = actual good units / planned good units
availability = operating time / planned production time
performance = ideal cycle time * total count / operating time
quality = good count / total count
OEE = availability * performance * quality
production gap = planned good units - actual good units
estimated lost units = lost time / governed ideal cycle time
```

Required output:

- scope, period, timezone, and current state;
- planned, total, good, scrap, and rework quantities;
- production variance and attainment;
- availability, performance, quality, and OEE where applicable;
- downtime and estimated lost units;
- comparison results and important deviations;
- observed versus calculated labels;
- formula version, provenance, completeness, latency, last timestamp, warnings, and confidence.

Guardrails:

- Do not infer root causes.
- Do not mix total-unit and good-unit targets.
- Do not use an assumed KPI formula when a governed definition is missing.
- Warn before calculating from incomplete or stale data.
- Distinguish exact observed values from estimates.

Handoff to `explain_performance_loss`:

```text
performance gap + time window + affected graph IDs
+ downtime/speed intervals + quality losses + production context
+ data-quality warnings + source-event references
```

### 11.3 Skill 2 - `explain_performance_loss`

**Professional role:** Industrial Engineer / Continuous Improvement Engineer / Reliability Analyst  
**Stage objective:** Convert the measured gap into quantified, evidence-supported loss drivers.  
**Related backlog:** O3, O4; OPT-R02-R03; OPT-C02; OPT-G01-G03 and G06.

Use for questions such as:

- Why did the line miss target?
- What reduced OEE?
- What caused the slowdown or downtime?
- How much did machine, material, labor, quality, or planning contribute?

Required inputs:

- current output from `measure_operational_performance` or a fresh equivalent analysis;
- equipment and station state timeline;
- downtime events and reason codes;
- material, alarm, sensor, operator, maintenance, quality, job/product, schedule, and shift context as available.

Authorized tools:

| Tool | Purpose |
|---|---|
| `read_loss_tree` | Retrieve governed loss decomposition and source references. |
| `read_bottleneck_candidates` | Retrieve ranked constraints with supporting and contradicting evidence. |
| `open_investigation`, `update_investigation` | Persist the analytical workflow and evidence. |
| `read_investigation` | Reuse a current investigation instead of recomputing blindly. |
| Operational Graph query | Traverse events, assets, orders, lots, shifts, material, failures, and defects. |
| Produce/Move/Monitor/Maintain/Inspect/Plan reads | Retrieve owning-domain evidence. |

Professional procedure:

1. Verify that the Measure result is current and sufficiently complete.
2. Decompose the gap into availability, speed/performance, quality, planning, and unclassified loss.
3. Build a time-aligned event timeline.
4. Match loss intervals to domain events and graph relationships.
5. Separate initiating causes, contributing factors, symptoms, and downstream effects.
6. Compare the affected run with a fair good-run cohort when possible.
7. Quantify minutes and units associated with every supported driver.
8. Rank drivers by impact.
9. Preserve unclassified loss and list missing evidence.
10. Record supporting and contradicting evidence for each hypothesis.

Confidence classes:

- **Confirmed:** consistent direct evidence supports the cause.
- **Probable:** strong evidence exists, but one material confirmation is missing.
- **Possible:** the pattern is compatible, but credible alternatives remain.
- **Unknown:** evidence is insufficient.

Required output:

- total gap and loss categories;
- cause, contributing factor, and symptom classification;
- event timeline and graph references;
- duration and estimated lost units per driver;
- percent of total loss explained and unclassified remainder;
- supporting and contradicting evidence;
- confidence per hypothesis;
- likely owning operational area and evidence still needed.

Guardrails:

- Do not treat correlation as confirmed causation.
- Do not assign blame to an operator without direct evidence.
- Do not use the latest alarm alone as root cause.
- Do not force all loss into known categories.
- Explain how much of the gap remains unknown.

Handoff to `predict_operational_risk`:

```text
confirmed/probable causes + repeating patterns + current conditions
+ sensor/material/maintenance trends + schedule context
+ evidence refs + uncertainty + unresolved data gaps
```

### 11.4 Skill 3 - `predict_operational_risk`

**Professional role:** Reliability Engineer / Production Forecaster / Predictive Analyst  
**Stage objective:** Estimate what is likely to happen, when it may happen, and its operational effect.  
**Related backlog:** O5; OPT-R06; OPT-C07; OPT-E12; OPT-G08.

Prediction families:

- end-of-hour or end-of-shift output and probability of meeting target;
- time to material depletion and starvation probability;
- failure, degradation, or repeated-stop risk;
- defect-rate or process-drift risk;
- queue, blockage, starvation, or bottleneck-migration risk.

Required inputs:

- current operational state and fresh Measure/Explain results;
- historical production and source-domain events;
- applicable sensor/time-series, maintenance, material, schedule, product/recipe, staffing, and quality context;
- forecast objective, horizon, decision threshold, and intervention deadline.

Authorized tools:

| Tool | Purpose |
|---|---|
| `run_forecast` | Execute a governed forecast with model and data-lineage metadata. |
| Optimize model registry read | Validate model scope, version, performance, and drift. |
| Monitor time-series read | Retrieve validated sensor/state features. |
| Produce/Move/Maintain/Inspect/Plan reads | Retrieve current state and exogenous features. |
| Operational Graph query | Resolve asset, product, operating mode, and prior-pattern context. |

Professional procedure:

1. Define predicted event, unit of analysis, horizon, and useful intervention deadline.
2. Retrieve the latest state and required features.
3. Confirm model applicability to asset, product, operating mode, and horizon.
4. Check feature freshness, missingness, drift, and training-domain distance.
5. Generate a baseline forecast or deterministic rule calculation.
6. Calculate probability or prediction interval.
7. Identify the factors most influencing the result.
8. Estimate operational impact and threshold-crossing time.
9. State whether the result is model-based, rule-based, or deterministic.

Required output:

- predicted event and expected time/window;
- horizon, probability, interval, and confidence;
- expected delay, lost units, quality, cost, or risk impact;
- primary influencing factors;
- intervention deadline;
- model/ruleset version and applicability;
- data freshness, missing features, drift, and warnings.

Guardrails:

- Never present a prediction as guaranteed.
- Always provide the horizon and uncertainty.
- Warn when operating outside the validated range.
- Reject or downgrade a forecast with stale critical features.
- Separate predictions from deterministic calculations.
- Do not imply causation from a predictive feature.

Handoff to `evaluate_operational_alternatives`:

```text
predicted event + timing + probability/interval + impact
+ intervention deadline + constraints + influencing factors
+ model applicability and uncertainty
```

### 11.5 Skill 4 - `evaluate_operational_alternatives`

**Professional role:** Operations Research Analyst / Production Planner / Industrial Engineer  
**Stage objective:** Generate feasible response options and compare consequences under real constraints.  
**Related backlog:** O7 and O9; OPT-R07-R08; OPT-C08; OPT-G07.

Use for questions such as:

- What options can avoid the shortage?
- Should we expedite material, move labor, reduce speed, or change sequence?
- Should maintenance happen now or after the batch?
- Can we recover the target, and at what cost or risk?

Required inputs:

- Measure, Explain, and Predict outputs that remain current;
- operational objective and decision deadline;
- schedule, material, labor/skills, asset capabilities, maintenance, quality, delivery, cost, energy, and safety constraints.

Authorized tools:

| Tool | Purpose |
|---|---|
| `run_scenario` | Execute a read-only governed what-if simulation. |
| Plan reads | Schedule, sequence, capacity, delivery priorities, and planning constraints. |
| Produce/Move/Maintain/Inspect reads | Current feasibility and source-domain capabilities. |
| Protect reads/policy | Hard safety and compliance constraints. |
| Cost/impact calculator | Governed cost, energy, delay, scrap, and benefit factors. |
| Constraint/solver service | Generate or rank feasible allocations and sequences. |

Professional procedure:

1. Define the objective function and decision deadline.
2. Retrieve hard constraints, soft preferences, and business priorities.
3. Include a do-nothing baseline when meaningful.
4. Generate multiple materially different alternatives.
5. Remove unsafe, prohibited, or technically infeasible options and state why.
6. Simulate remaining options with versioned inputs and models.
7. Compare throughput, service, cost, quality, safety, labor, maintenance, energy, WIP, and complexity.
8. Test uncertain assumptions with sensitivity analysis.
9. Identify cross-line or downstream harm and residual risks.
10. Rank alternatives without executing them.

Required output per option:

- feasibility and violated constraints if infeasible;
- additional output or loss avoided;
- schedule and delivery impact;
- cost and energy impact;
- quality, safety, equipment, and labor risk;
- resources required and implementation time;
- reversibility, assumptions, confidence, and sensitivity;
- ranked position and decision deadline.

Guardrails:

- Unsafe or prohibited actions cannot be presented as valid options.
- Do not optimize output alone.
- Distinguish hard constraints from preferences.
- Show all material simulation assumptions.
- Say "best among evaluated options," not globally optimal, unless proven by the solver formulation.
- Do not write any operational change in this stage.

Handoff to `recommend_operational_action`:

```text
ranked feasible options + expected benefits/costs + residual risks
+ assumptions/sensitivity + deadline + approvals
+ action boundaries + do-nothing baseline
```

### 11.6 Skill 5 - `recommend_operational_action`

**Professional role:** Operations Manager / Shift Manager / Decision-Support Specialist  
**Stage objective:** Select the preferred option using priorities, risk tolerance, and authorization policy; recommend, prepare, or execute only within the allowed mode.  
**Related backlog:** O6; OPT-R04; OPT-C03-C06; OPT-G04-G05 and G09.

Decision modes:

- **Advisory:** return a recommendation only.
- **Approval required:** prepare a decision packet and wait.
- **Guarded automation:** execute a predefined low/medium-risk action within an approved policy.
- **Autonomous:** only pre-authorized, reversible, auditable actions inside explicit limits. This mode does not permit critical control changes.

Required inputs:

- ranked alternatives and current conditions;
- business priorities, risk tolerance, action deadline, and cost thresholds;
- principal, role, autonomy, allowed actions, and approval policy.

Authorized tools:

| Tool | Purpose |
|---|---|
| `draft_recommendation` | Persist evidence, expected impact, assumptions, constraints, and rollback. |
| `decide_recommendation` | Record an authorized accept/modify/reject/defer/more-evidence decision. |
| `create_experiment` | Convert an accepted recommendation into a governed improvement workflow. |
| SDK decision packet | Obtain approval before a gated command. |
| Context and policy reads | Confirm current principal, autonomy, allowed actions, and risk rules. |
| Owning-module command | Execute only after approval and only within the owning domain. |

Professional procedure:

1. Revalidate data, option feasibility, and deadline.
2. Apply current business priorities and policy constraints.
3. Select the preferred option and explain why.
4. Show the important trade-offs and alternatives considered.
5. State expected benefit, cost, confidence, residual risk, owner, and stop/rollback conditions.
6. Determine required approvals and SDK risk class.
7. Recommend, prepare, or execute only according to the allowed mode.
8. Record decision rationale, actor, version, and approval state.

Required output:

- recommended action and reason;
- supporting evidence and alternatives considered;
- expected benefit/cost and residual risks;
- assumptions, constraints, owner, and deadline;
- required approvals and execution mode;
- rollback/stop conditions;
- recommendation ID, decision ID, actor, and audit reference.

Guardrails:

- Do not exceed the principal's authorization.
- Require approval for high-risk, safety-critical, quality-critical, or material schedule changes.
- Revalidate immediately before execution.
- Do not hide trade-offs or contradictory evidence.
- Prefer reversible action under high uncertainty.
- Do not report an action as executed until the owning module confirms the write.

Handoff to `replan_and_dispatch_operations`:

```text
approved decision + exact action payload + owning modules
+ owners/deadlines/dependencies + approval proof
+ expected outcome + rollback/stop conditions
```

### 11.7 Skill 6 - `replan_and_dispatch_operations`

**Professional role:** Production Planner / Dispatch Coordinator / Operations Control Specialist  
**Stage objective:** Convert an approved decision into coordinated, version-safe commands across owning modules and verify execution.  
**Related backlog:** O7, O8; OPT-C06 and C09-C11; OPT-G09.

Use only after a recommendation is approved or a policy explicitly authorizes the action.

Authorized tools:

| Target module | Typed action examples |
|---|---|
| Plan | Submit scenario proposal; request approved sequence or schedule revision. |
| Produce | Create/reprioritize an operational task or update a permitted job queue. |
| Move | Create/reprioritize pallet movement or replenishment task. |
| Maintain | Create/prioritize inspection or maintenance work request. |
| Inspect | Request inspection or an approved quality workflow; never bypass quality authority. |
| Workforce/notifications through owning module | Assign/notify responsible people and request acknowledgement. |

Optimize must never write directly to these modules' databases or directly to APS, MES, WMS, CMMS, QMS, or PLC systems. The owning module may use its controlled adapter internally.

Professional procedure:

1. Retrieve current plan and operational state.
2. Verify approval, principal, action version, deadline, and continuing feasibility.
3. Detect whether relevant state changed after approval.
4. Prepare versioned command payloads with idempotency keys.
5. Validate resource, material, labor, machine, quality, delivery, and Protect constraints.
6. Calculate downstream effects and identify all affected owners.
7. Submit commands in a safe transaction/saga order.
8. Confirm every owning-module response before claiming success.
9. Notify affected users and request acknowledgement when required.
10. Monitor task milestones and operational events.
11. Roll back compensatable steps or escalate partial failure.
12. Trigger `measure_operational_performance` at the defined checkpoint.

Safe transaction/saga sequence:

```text
revalidate current state
-> prepare/version proposed changes
-> obtain or confirm approval
-> submit Plan change if required
-> create execution tasks in owning modules
-> confirm writes and task IDs
-> notify and obtain acknowledgements
-> monitor outcome events
-> compensate or escalate partial failure
-> re-measure and validate benefit
```

Required output:

- changed plan/jobs and source version;
- material, labor, maintenance, inspection, and production tasks;
- affected orders and revised times;
- command responses and idempotency IDs;
- notifications and acknowledgements;
- execution, partial-failure, compensation, and rollback status;
- next checkpoint and expected outcome.

Guardrails:

- Never write without approved authority.
- Do not overwrite state changed since approval.
- Prevent duplicates with idempotency and correlation IDs.
- Preserve original state and compensating actions.
- Treat task creation and task completion as different events.
- Escalate rejected, expired, unacknowledged, or partially failed actions.
- Critical machine/process setpoints remain out of scope by default.

Closed-loop handoff:

Call `measure_operational_performance` after the action's measurement delay, then link the new measurement to the recommendation, decision, tasks, and experiment. If expected improvement did not occur or new risk emerged, open a new cycle instead of declaring success.

### 11.8 Skill routing logic

| User intent | Primary skill |
|---|---|
| What happened? How are we performing? | `measure_operational_performance` |
| Why did it happen? | `explain_performance_loss` |
| What will happen next? | `predict_operational_risk` |
| What options do we have? | `evaluate_operational_alternatives` |
| What should we do? | `recommend_operational_action` |
| Apply the approved decision. | `replan_and_dispatch_operations` |

Multi-stage examples:

| Request | Required route |
|---|---|
| Why are we behind? | Measure -> Explain |
| Will we recover by end of shift? | Measure -> Explain if needed -> Predict |
| Why are we behind and what should we do? | Measure -> Explain -> Predict -> Evaluate -> Recommend |
| Apply the approved recovery plan. | Revalidate Measure -> Re-plan/Dispatch -> Measure again |

Do not skip a stage unless a compatible output already exists, is still fresh, uses the same scope and governed definitions, and has no unresolved warning that invalidates the next stage.

### 11.9 Shared response contract

Every skill returns the same envelope, with skill-specific content inside `result`:

```json
{
  "skill": "measure_operational_performance",
  "status": "completed",
  "execution_id": "OPT-20260715-00142",
  "correlation_id": "cycle-line2-shift-a-20260715",
  "scope": {
    "plant_id": "plant-a",
    "line_id": "line-2",
    "asset_id": null,
    "product_id": null,
    "order_id": null,
    "time_start": "2026-07-15T06:00:00+07:00",
    "time_end": "2026-07-15T14:00:00+07:00",
    "timezone": "Asia/Bangkok"
  },
  "summary": "Human-readable operational result",
  "result": {},
  "observations": [],
  "calculations": [],
  "inferences": [],
  "predictions": [],
  "recommendations": [],
  "constraints": [],
  "assumptions": [],
  "data_quality": {
    "completeness": 0.97,
    "latest_timestamp": "2026-07-15T13:58:42+07:00",
    "latency_seconds": 78,
    "conflicts": [],
    "warnings": []
  },
  "confidence": {
    "level": "high",
    "score": 0.89,
    "explanation": "Evidence is consistent across first-party Produce, Move, and Monitor events."
  },
  "provenance": {
    "source_event_ids": [],
    "graph_node_ids": [],
    "module_reads": [],
    "legacy_adapter_reads": []
  },
  "audit": {
    "principal": {},
    "session_id": "session-id",
    "tools_used": [],
    "kpi_definition_versions": [],
    "ruleset_version": "1.0",
    "model_versions": [],
    "approval_ids": [],
    "write_results": []
  },
  "recommended_next_skill": "explain_performance_loss",
  "handoff": {}
}
```

Required semantic labels:

- **Observed:** directly recorded first-party or adapter fact.
- **Calculated:** derived using a versioned formula.
- **Inferred:** evidence-supported analytical conclusion.
- **Predicted:** future estimate from a declared model or rule.
- **Recommended:** proposed decision under objectives and constraints.
- **Approved:** accepted by an authorized principal or policy.
- **Executed:** confirmed successful by the owning module.
- **Validated:** outcome measured against an approved baseline method.

### 11.10 Skill-level acceptance criteria

A skill is not complete until:

- its tool allowlist and prohibited tools are explicit;
- its input and output JSON Schemas are versioned;
- entity IDs, time window, timezone, freshness, and provenance are present;
- missing or conflicting data produces a structured warning or fail-closed result;
- every calculation identifies the governed formula version;
- every inference shows evidence and contradictory evidence where relevant;
- every prediction shows horizon, uncertainty, applicability, and model/ruleset version;
- every recommendation shows alternatives, constraints, approvals, and rollback/stop conditions;
- every write uses a gated owning-module command and records the result;
- the next-skill handoff is machine-validatable;
- replay, idempotency, stale-state, partial-failure, and unauthorized-action tests pass.

## 12. Definition of done and guardrails

### 12.1 Data and analytical correctness

- Results are reproducible from versioned definitions and source event references.
- Time zones, shift boundaries, late events, duplicated events, and corrections have explicit handling.
- KPI results expose freshness, completeness, and coverage.
- Comparisons disclose cohort and baseline selection.
- Hypotheses separate correlation from confirmed cause.
- Confidence is calibrated and never replaces evidence.
- Financial, energy, or capacity benefit shows the factors and method used.

### 12.2 SDK and module correctness

- Module runs independently without importing Minder Core code.
- Manifest publishes typed input and output schemas.
- Reads are side-effect free.
- Every write is typed, risk classified, idempotent where necessary, and auditable.
- Known failures return structured errors, not generic 500s.
- High-risk actions produce decision packets before any source module changes.
- Accepted writes emit domain events back to the first-party event log.
- Background jobs stream progress or reverse-push results.
- UI snapshots accurately describe current page, visible data, and actions.
- Stale snapshot deltas recover by sending a full snapshot.

### 12.3 Human control and safety

- Recommendation cards include evidence, assumptions, confidence, constraints, expected impact, side effects, and rollback/stop conditions.
- A human can approve, modify, reject, defer, or request more evidence.
- All decisions record actor, role, timestamp, version, and reason.
- Protect constraints can veto or narrow a recommendation.
- Schedule, quality, maintenance, material, and control actions are executed only by the owning module.
- Critical control changes are unavailable by default.
- Autonomy expands only after measured decision quality, action reliability, rollback success, and user trust meet approved thresholds.

## 13. Open product decisions requiring approval

Before implementation commits to irreversible data or API design, confirm:

1. The first Optimize deployment scope: one line, one plant, or multi-site.
2. The authoritative source and exact formula for OEE and each loss category.
3. Whether Produce remains the source of live OEE while Optimize owns deeper analysis.
4. The first target persona and weekly decision ritual.
5. Which upstream domains exist at MVP besides Produce.
6. Required data retention, correction, and audit policies.
7. Approved benefit-validation methods and financial factors.
8. The initial set of allowed cross-module actions.
9. The policy mapping between SDK autonomy values and industrial L1-L5 levels.
10. The minimum gate-maturity metrics required before high-risk commands are enabled.
11. Whether prediction and simulation are separate services or internal Optimize capabilities.
12. Tenant, plant, role, and data-residency boundaries.

## 14. Concise build order

For the next AI engineering session, proceed in this order:

1. Confirm open decisions that affect entity identity, KPI semantics, or MVP scope.
2. Define versioned event contracts and stable graph IDs.
3. Scaffold the independent Optimize module from `modules/module_template`.
4. Implement O1 configuration and data-readiness checks.
5. Implement O2 KPI calculation with provenance and tests.
6. Implement O3 loss tree, Pareto, and bottleneck evidence.
7. Implement O4 investigation workflow and graph traversal.
8. Implement O6 recommendation and human decision workflow.
9. Implement O8 experiments and benefit validation.
10. Add SDK Core, then reads/events, then guidance, then low/medium-risk commands.
11. Implement versioned skill contracts and routing for `measure_operational_performance` and `explain_performance_loss`.
12. Implement `recommend_operational_action` in advisory and approval-required modes, then connect it to the experiment workflow.
13. Verify one complete Measure -> Explain -> Recommend -> Approve -> Task -> Measure loop end to end.
14. Add `predict_operational_risk` and `evaluate_operational_alternatives` after model and simulation governance exists.
15. Enable `replan_and_dispatch_operations` only after owning-module commands, Protect constraints, saga recovery, and gate-maturity requirements pass.
16. Add energy optimization and high-risk action proposals only after the corresponding data and autonomy maturity gates are met.
