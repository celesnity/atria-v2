# Embinder x Atria capability matrix

Embinders operate declared Atria browser capabilities only. They never receive a
direct IoTMock endpoint, relay approval token, or access to an iframe DOM.

| Surface | Capability | User intent | Risk | Confirmation | Result |
| --- | --- | --- | --- | --- | --- |
| App shell | `current_screen` | Inspect current route, module, tab, and visible actions | Read | None | Bounded current-screen context |
| App shell | `ui_navigate` | Open Chat or tenant administration | Read | None | Real React Router transition |
| Administration | `atria_open_tenant_users` | Open a tenant's user page | Read | None | Guarded route transition for the supplied tenant slug |
| Module shell | `atria_open_module` | Open a discovered module | Read | None | Normal module workspace transition |
| Module shell | `atria_select_module_tab` | Open a discovered module tab | Read | None | Normal declared-tab transition |
| Optimize Guided iframe | `optimize_navigate_section` | Open Today, Decisions, Performance, or History | Read | None | Real Guided `state.view` transition |
| Optimize Guided iframe | `optimize_open_recommendation` | Inspect a visible recommendation | Read | None | Active recommendation opens in Guided |
| Optimize Guided iframe | `optimize_open_evidence` | Inspect evidence | Read | None | Evidence drawer opens |
| Optimize Guided iframe | `optimize_open_review` | Inspect a proposed decision | Read | None | Review drawer opens without execution |
| Optimize Guided iframe | `optimize_set_language` | Change UI language | Write | None | Reversible EN/VI presentation change |
| Optimize Guided iframe | `optimize_set_theme` | Change UI theme | Write | None | Reversible light/dark presentation change |
| Optimize Guided iframe | `optimize_set_data_mode` | Select live or labelled demo data | Write | None | Reversible mode change |
| Optimize Guided iframe | `optimize_approve_recommendation` | Approve and dispatch the visible recommendation | Destructive | Explicit Approve/Deny | Governed approval then owning-module dispatch; no success claim before module confirmation |
| Optimize Guided iframe | `optimize_reject_recommendation` | Record a rejection | Destructive | Explicit Approve/Deny | Recorded governed decision without dispatch |
| Operations | `atria_read_operational_truth` | Inspect fleet condition | Read | None | Grounded Monitor facts and evidence |
| Operations | `atria_request_release_order` | Request product intake release | Destructive | Explicit Approve/Deny | Pending governed operation with correlation id |
| Operations | `atria_request_service_order` | Request machine service | Destructive | Explicit Approve/Deny | Pending governed operation with correlation id |

## Platform contract

- React owns relay registration, policy, React Router navigation, and live app context.
- The sandboxed Guided iframe publishes bounded context and receives named calls through the
  typed host bridge. The host validates `event.source` before forwarding either direction.
- The iframe never receives a relay token and the host never scrapes the iframe DOM.
- Every tool is tied to an existing application route, store transition, or Guided action. The
  agent does not invent parallel business logic.

## Safety rules

- Monitor remains read-only.
- IoTMock is the only actuator and is reached only by Optimize after approval.
- Embinder's policy gate applies before a browser tool runs; Optimize's decision gate applies
  before a plant action runs. A request is not an execution.
- Navigation and inspection do not request confirmation. Recorded decisions, orders, and
  equipment-affecting actions always do.
- The Atria operations API records an idempotency key and operation id. Repeating the same
  request returns the original pending or completed operation.
