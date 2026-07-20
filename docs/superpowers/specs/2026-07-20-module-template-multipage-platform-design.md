# Module Template multi-page platform design

## Goal

Turn the current Module Template operations screen into a coherent, interactive
four-page platform. It must demonstrate the Embinder React SDK, the direct
Minder WebSocket UI bridge, and approval-gated actions without using MCP,
Python connectors, workers, or Celery.

## Scope

The frontend is the only module application. It serves from the existing
Module Federation remote and retains the existing `@embinder/react` provider,
direct UI descriptor adapter, relay container, and Minder-hosted WebSocket
bridge.

The UI contains four navigable pages:

- **Mission Control** shows platform health, key metrics, the active incident,
  agent status, and a concise incident timeline. It provides orchestration
  actions such as opening an incident and starting a response.
- **Incident & Data Analyst** shows the simulated incident list, a selected
  incident detail panel, an interpretable data chart, and analysis/triage/
  mitigation actions.
- **Workflow & Approvals** shows mitigation proposals and their lifecycle.
  Approve, reject, and escalation actions are explicit controls. Approval
  transitions are sent through the Embinder direct relay gate; the relay keeps
  MCP and chat endpoints disabled.
- **Activity & Audit** shows user and agent actions as a chronological audit
  trail, including status and the correlation ID returned by the action path
  when one is available.

## Shared interaction model

`PlatformStore` is the single React state boundary for the demonstration. It
holds the selected incident, risk score, workflow/proposal state, agent state,
and audit entries. It starts with deterministic simulated data so the
showcase is immediately useful after a refresh. UI actions update state and
append audit records; page changes preserve that state.

Every agent-operable control registers a stable descriptor through the
existing `Agent.Button` adapter. Each descriptor includes an action name,
human-readable label, a page/context description, and the selection it
operates on. Data/context descriptors expose a compact current snapshot rather
than raw component implementation details.

When Minder calls `ui_describe`, it receives the registered descriptors and
current context. When it calls `ui_act`, the host sends the command over its
existing WebSocket to the module. The module runs the action, returns a result
using the correlation ID, updates the store, and writes an activity entry. The
Embinder visualization provider supplies the single ghost cursor and moves it
to the invoked control. The legacy custom ghost cursor is not mounted.

## Approval boundary

Only destructive workflow decisions (`approve_escalation`, `reject_escalation`
and any equivalent final decision) use the relay's `/internal/direct-call`
path. The direct token and policy remain local-container configuration. The
relay policy names each allowed action, records audits, binds to the Docker
network, and continues to disable MCP and chat routes. Read-only analysis and
non-destructive state transitions stay on the direct WebSocket bridge.

Human clicks remain available for the showcase, but they invoke the same
store-level command functions as agent actions. A final approval action must
not be represented as a cosmetic local state flip that bypasses the relay.

## Navigation and visual behavior

The module has a persistent, accessible left navigation rail and a page header
that names the current surface. The content area is responsive and uses
semantic buttons with visible focus and disabled states. Action controls sit
inside labelled action panels, never as adjacent unstyled text. The mascot
appears exactly once inside the chat/host viewport; Embinder supplies exactly
one ghost cursor in the module content viewport.

## Error handling

An unavailable direct bridge or relay leaves the page usable for inspection,
marks the relevant action as failed, and appends a failed activity record with
a short actionable error. A timed-out action is not assumed successful. The
page displays a compact status notice, without crashing the module remote.

## Verification

- Add focused unit tests for the platform reducer/store and action registration
  contracts, including the final approval routing contract.
- Run the module frontend test script and production build.
- Rebuild the Module Template Docker service and verify its remote entry is
  served.
- Run the relevant Python bridge tests and confirm disabled MCP routes remain
  unavailable on the relay.
- Exercise an end-to-end browser/session flow: describe the platform, select
  an incident, analyze it, request approval, approve it, and confirm the audit
  entry plus cursor behavior.

## Explicit non-goals

This is a deterministic interactive platform showcase, not a production
incident system. It does not add a Python module API, connector registration,
heartbeat, Celery worker, MCP endpoint, SDK chat bubble, external database, or
real analytics backend.
