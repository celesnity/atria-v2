---
name: optimize_demo
description: Optimize Console demo - a real-time manufacturing decision engine that detects a production line will miss its shift target, explains the loss, forecasts the outcome, evaluates recovery actions against operational constraints, and returns a versioned, executable recommendation. Open the dashboard to run the demo; scripts/optimize.py only persists decision history + audit events.
---

# optimize_demo

**Optimize Console — a manufacturing decision engine (demo).**

Detects that a production line is likely to miss its shift target, quantifies
and explains the loss, forecasts end-of-shift output, evaluates a small set of
recovery actions against operational constraints (blocking unsafe ones even when
they recover the most units), ranks the feasible actions with a configurable
weighted score, and returns a **versioned JSON decision object** plus mock
downstream commands and audit events.

Core loop: **Measure → Explain → Predict → Evaluate → Recommend → Approve →
Re-plan**, demonstrated across 5 replayable scenarios for one plant / one line /
one work order / one shift.

## When to use

Demonstrating production-recovery decisioning for a single line: detect a
forecast miss, explain the causes, compare recovery alternatives, reject
infeasible ones, approve/dispatch a recommendation to a mock Move/Plan module,
and track expected-vs-actual outcome. This is a self-contained demo — it does
not connect to a real MES/PLC.

## Dashboard

Open the **Optimize** tile. The demo control bar picks one of 5 scenarios and
drives the loop: inject the scenario event → the forecast drops and a
recommendation is generated → approve (where required) → Send to Move/Plan →
simulate execution → expected-vs-actual outcome. The **Alternatives** tab shows
the constraint-checked, scored comparison; **Recommendation** shows the decision
object and lifecycle actions; **View decision JSON** opens the decision object /
downstream command / API response / audit-event drawer. All decision math runs
client-side; the dashboard is the source of truth.

The 5 scenarios:
1. Material starvation -> prioritize pallet delivery (no approval).
2. Resource reassignment -> move an operator (supervisor approval).
3. Sequence change -> reorder jobs (planner approval).
4. Unsafe high-speed option -> **rejected** on the machine-health constraint.
5. Recommendation invalidated -> **supersede** v1 and recalculate to v2.

## Runbook (scripts/optimize.py — persistence only)

All commands run from `modules/optimize_demo/`. Each reads a JSON payload on
stdin and prints a JSON result on stdout (this is what the dashboard calls via
the AtriaDash bridge). Decision history + audit events are stored under `data/`
(JSON files, bootstrapped on first write).

- Save / version a decision object — `python scripts/optimize.py save`
  (stdin: the decision object; marks a prior version `superseded` when
  `supersedes_version` is set; appends a `recommendation_created` audit event).
- Get one decision — `python scripts/optimize.py get` (stdin:
  `{"recommendation_id": "REC-...", "version": 2}`; omit version for latest).
- List decision history — `python scripts/optimize.py list`.
- Approve / Reject — `python scripts/optimize.py approve` /
  `python scripts/optimize.py reject` (stdin: `{"recommendation_id", "actor"}`).
- Dispatch to a mock module — `python scripts/optimize.py dispatch`
  (stdin: `{"recommendation_id", "target_module", "command"}`; returns a mock
  `{"status": "accepted", "task_id": "MOVE-TASK-..."}` and appends an audit
  event).
- Read the audit trail — `python scripts/optimize.py audit`.

Python never re-derives forecasts/scores/constraints — it only persists what the
dashboard computed, so the ranking/constraint logic has a single source of truth
in the dashboard.
