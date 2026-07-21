---
name: monitor
description: Read-only operational sensing for Produce and Optimize. Converts IIOT observations into versioned operational state, contextual events, evidence packages, source health, production facts, losses, constraints, and intervention outcomes.
---

# Monitor

Monitor is the shared sensory layer. It observes and explains; it never changes production records,
machine settings, schedules, quality holds, or safety controls.

## Preferred SDK reads

- `monitor_live_operations`: canonical identity, work context, operating state, asset condition,
  data health, source health, and observations.
- `monitor_event_timeline`: ordered operational facts with semantic labels, consumer routing,
  evidence references, and provenance.
- `monitor_event_evidence`: source observations, health, conflicts, and provenance for one event.
- `monitor_source_health`: connection, quality, freshness, clock, and calibration status.
- `monitor_produce_data_product`: equipment state, cycle facts, downtime candidates, context, and
  evidence for Produce. This read contract does not update Produce.
- `monitor_optimize_data_product`: normalized losses, live constraints, invalidation signals,
  readiness, and intervention outcomes. This read contract does not execute recommendations.
- `monitor_fleet`, `monitor_machine`, and `monitor_ask`: compatibility reads for fleet drill-down
  and grounded questions.

All operational reads are `@conn.read` or explicitly read-only and therefore risk `none`. The only
low-risk declaration is the SDK-generated UI navigation command.

## Events

The connector publishes versioned operational facts such as `production_cycle_completed`,
`micro_stop_detected`, `material_starvation_detected`, `production_loss_event`, and
`intervention_outcome_recorded`. They come from a background poller over unseen simulator sequence
numbers, not as side effects of a user read.

## Dashboard

The React Module-Federation dashboard has five task-oriented views: Live Operations, Event Timeline,
Assets, Data Health, and Data Products. It uses `minder_ui_sdk` declarations (`Agent.Page` and
`Agent.Data`) so agents read declared state instead of scraping the DOM. It supports keyboard focus,
reduced motion, mobile navigation, 44-pixel controls, loading skeletons, and explicit error recovery.
Light/dark appearance and English/Vietnamese language preferences are owned by Monitor and persist
locally. Data Products provides separate Overview, Produce, and Optimize consumer modes while
remaining read-only.

## Simulator

Use the laundry domain in `D:\[Research]_IIOT\[Project]_IOTMock`. It models five washers and five
dryers and exposes the following additive Monitor endpoints:

- `GET /api/v2/operations/snapshot`
- `GET /api/v2/operations/events?since=0&limit=100`
- `GET /api/v2/operations/events/{event_id}/evidence`

Monitor preserves the legacy fleet endpoints for existing screens and scripts.

From the project root, `run-monitor.ps1` builds the dashboard when needed, reuses or starts the
laundry simulator, validates its 10-machine `monitor.operations.v1` contract, and starts Monitor at
`http://localhost:9310/dashboard/index.html`. Pass `-NoSimulator` only when intentionally testing
the stable disconnected UI.
