# Module Template Embinder Platform Design

## Goal

Turn `modules/module_template` into a normal, self-contained operations platform
showcase that demonstrates the real Embinder React SDK together with Minder's
existing direct UI bridge. The platform uses deterministic simulated data so an
agent can repeatedly inspect, analyze, triage, and approve a scenario without a
connector, Python worker, Celery task, module REST API, or MCP.

## Non-negotiable boundaries

- Minder Core remains the only chat and agent runtime. The Embinder `ChatBubble`
  is disabled.
- The direct Minder WebSocket bridge remains the only path from the Minder agent
  to the module: `ui_describe` reads state and `ui_act` invokes an action.
- An embedded Embinder relay is permitted only for the SDK's browser protocol,
  policy gate, approval decisions, spotlight, and audit trail. Its MCP endpoint
  is disabled and no MCP client is used.
- The module remains a UI-only static federation remote. The legacy connector
  registration, heartbeat, health APIs, Python backend, worker, and Celery are
  not reintroduced.

## Platform surface

The dashboard is a persistent operations platform rather than a scripted demo.
It contains:

- An overview with risk score, throughput, model confidence, and live simulated
  event stream.
- An incident collection with selected incident details and analyst findings.
- A triage board that places incidents in workflow lanes.
- A proposal form and an approval queue.
- An activity and audit panel that shows actions, gate status, and the final
  decision.

All initial incidents, metrics, and event timestamps are deterministic. A reset
action returns the platform to that initial state.

## Embinder SDK integration

Use the public React SDK rather than duplicating its UI semantics:

- `EmbinderProvider` runs with visualisation enabled and SDK chat disabled.
  The provider points to the embedded relay's app protocol.
- `AgentScope` exposes bounded live context for Overview, Analysis, Triage, and
  Approvals so the agent sees the screen-level state that a user sees.
- `AgentList` exposes incident and proposal collections. The agent receives
  stable IDs and can select, analyze, escalate, or inspect individual records.
- `AgentForm` collects a mitigation proposal with typed field values.
- `AgentInput`, `AgentSelect`, `AgentToggle`, `AgentCheckbox`, and
  `AgentRadioGroup` make the proposal controls agent-drivable with their live DOM
  state.
- `AgentButton`, `AgentLink`, and `AgentDiv` expose primary actions, drill-down,
  and semantic read-only regions.
- `useScrollTarget`, `useRoute`, `useDraggable`, and `useDropZone` expose the
  page navigation and triage movement actions.
- Embinder's ghost cursor and spotlight reflect action phases. Minder's existing
  tool-phase cursor event continues to provide feedback before an SDK action is
  dispatched.

## Agent and approval data flow

1. On module mount, the SDK registers rendered pointers, scopes, state, and
   action descriptors with the relay. The module also publishes equivalent
   descriptors through the direct bridge for `ui_describe`.
2. The Minder agent calls `ui_describe` and receives current platform context,
   available visible actions, incidents, proposals, and gate state.
3. The Minder agent calls `ui_act`. The direct bridge maps the requested action
   to the SDK-registered handler instead of maintaining a separate action
   implementation.
4. Read and ordinary write actions execute in the browser. A destructive action
   such as approving an escalation is passed through the relay's policy gate.
5. The gate canonicalizes arguments, emits spotlight and lock phases, waits for a
   human Approve or Deny decision, records the result in the audit stream, then
   either dispatches the browser handler or returns the rejection to the agent.
6. The module updates the local dashboard state and republishes its direct bridge
   context. Subsequent `ui_describe` calls see the new state.

## Policy and runtime configuration

The embedded relay has a dedicated module policy. Context reads, selection,
scrolling, filtering, and analysis are read/write. Moving an incident is write.
Creating or approving an escalation is destructive and must require approval.
The relay exposes only the app and approval protocol routes required by the
browser; it does not mount an MCP transport.

The relay lifecycle is provided by the module's UI-serving runtime or an
adjacent internal service in the module compose configuration. It is never
registered with Minder Core as a connector.

## Error handling

- If the relay is unavailable, the platform still renders and the direct bridge
  reports the unavailable approval capability instead of silently performing a
  destructive action.
- A denied or timed-out approval leaves the underlying proposal unchanged and
  writes a visible failed decision entry.
- An action that leaves the screen during execution returns a clear error and
  does not mutate state.
- The UI disables a control while a matching action or approval is pending.

## Verification

- Unit tests cover initial simulated platform state, descriptor/context
  publication, action transitions, reset behavior, and destructive-action gate
  outcomes.
- Relay integration tests prove its MCP routes are absent, policy risk mapping is
  applied, approve executes once, and deny performs no mutation.
- Existing direct UI bridge tests continue to prove request correlation and
  session isolation.
- Build both `web-ui` and the module federation remote. Run the module with the
  embedded relay and perform an end-to-end browser/agent flow: describe, select,
  analyze, create proposal, request approval, approve, and re-describe.
