# Federated Chat Blocks — Design

**Date:** 2026-07-10
**Status:** Approved (design); implementation not started
**Depends on:** the service-module federation work merged 2026-07-09
(`docs/superpowers/specs/2026-07-09-service-module-federation-design.md`).
**Reference module:** `maintenance_copilot`.

## Summary

Let a **service-module** (an out-of-process, containerized module) push its **own
React components** into the Atria chat stream, rendered **natively in-host** via
Module Federation — not as an iframe and not as a host-coded card. Blocks are
**interactive, live-updatable, and can act back** (call their own connector or
inject a chat message). They arrive two ways: as the result of an agent tool
call, and via a proactive, Keycloak-authenticated reverse push from the service.
The design reuses the federation stack (`federation.ts`, the `RemoteDashboard`
render pattern) and the existing `custom_block` WS + persistence machinery, adding
one block *variant* rather than a parallel system.

## Motivation

After the service-module extraction, a module's UI is a Module Federation remote
(the dashboard renders natively in-host). But the chat-block system only knows two
render models: **iframes** of `modules/<name>/blocks/*.html` from the Atria host's
disk, and **host-coded card components** keyed on a `type` string (e.g.
`maintenance_answer` → `MaintenanceAnswerBlock`). Neither lets a service-module
render *its own* component natively in the chat. This design closes that gap so a
module's chat UI is as deeply integrated as its dashboard.

## Decisions (locked during brainstorming)

1. **Rendering model:** federated React component, rendered natively in-host
   (shares the host's React/WS/store). Not iframe, not host-coded card.
2. **Trigger:** both — (a) as an agent tool-call response, and (b) proactive /
   streaming server-push from the service.
3. **Interactivity:** full duplex — blocks are live-updatable (update/remove after
   posting) and can act back (call their connector via `apiBase`, and/or inject a
   chat message via `sendMessage`).
4. **Auth for proactive push:** Keycloak. The service authenticates as its own
   Keycloak client (service account, client-credentials grant); the reverse
   ingress validates a service-principal token distinct from human login.

## Context (as-is)

- `atria/web/ui_bridge.py` — `push_block`/`update_block`/`remove_block` broadcast
  `custom_block` / `custom_block_update` / `custom_block_remove` WS events
  (`atria/web/protocol.py:WSMessageType`) and persist a `custom_block` ChatMessage
  so blocks survive reload. Today a block is an iframe of
  `modules/<name>/blocks/<block>.html`.
- `atria/web/routes/blocks.py` — `POST /api/blocks/{push,update,remove}`: an
  HTTP gateway around `ui_bridge` for **out-of-process** callers (subprocess
  scripts today), targeting a session by `session_id`.
- The service-module proxy tool (`atria/core/modules/remote.py`
  `build_remote_tool_specs._make_handler`) already re-broadcasts a structured
  `card` to the chat via `ctx.broadcaster` as a WS event.
- Module Federation is live: `web-ui/src/lib/federation.ts`
  (`registerRemote`/`loadRemoteComponent`) and
  `web-ui/src/components/ModuleDashboard/RemoteDashboard.tsx` render a module's
  remote natively in-host. The module's `frontend/vite.config.ts` `exposes`
  components (currently `./Dashboard`).
- Auth: `atria/web/dependencies/auth.py:require_authenticated_user` resolves a
  user via session cookie, **Keycloak bearer token** (`_resolve_via_bearer` →
  `routes/auth.py:verify_token`), or anonymous fallback. Keycloak runs in compose
  with a realm import (`keycloak/realm-export.json`) and a confidential backend
  client (`atria-backend`).

## Architecture

### 1. The remote-block descriptor

One payload shape flows through both feeders, the WS event, persistence, and the
renderer:

```jsonc
{
  "block_id": "b-<uuid>",        // service-generated → update/remove with no round-trip
  "render": "remote",            // discriminator vs existing iframe blocks (default "iframe")
  "module": "maintenance_copilot",
  "remote_name": "maintenance_copilot",  // MF remote name; matches manifest.remote.name
  "remote_entry": "http://localhost:9200/dashboard/remoteEntry.js",  // browser-facing URL
  "component": "./AlertsBlock",  // an exposed key from the module's FE federation config
  "props": { "...": "module-defined" },
  "api_base": "http://localhost:9200",   // derived from remote_entry; block calls its own connector
  "title": "Restock alerts",
  "height": "auto",
  "persist": true
}
```

The module declares chat-mountable components in `frontend/vite.config.ts`
`exposes` alongside `./Dashboard`, e.g.
`"./AlertsBlock": "./src/blocks/AlertsBlock.tsx"`. Rendering needs only the
descriptor; the manifest may list exposed block components for discoverability but
that is not required.

### 2. WS protocol + persistence (extend, don't replace)

Reuse the existing `custom_block` / `custom_block_update` / `custom_block_remove`
WS types and the `custom_block` ChatMessage persistence, carrying the descriptor
(with `render:"remote"`) instead of an iframe path. Iframe blocks (`render` absent
or `"iframe"`) are unchanged; the frontend branches on `render`.

`ui_bridge` gains `push_remote_block(descriptor, session_id, persist)` — a sibling
to `push_block` that broadcasts the same WS envelope and persists the same message
shape with the descriptor payload. `update_block`/`remove_block` are reused as-is
(they key on `block_id`).

### 3. Feeder 1 — tool-response path

Extend the proxy tool handler: if a connector tool response includes
`blocks: [descriptor, …]`, `_make_handler` calls
`ui_bridge.push_remote_block(...)` for each, using the **session from the agent's
context** (broadcast + persist). This rides Atria's in-process broadcaster exactly
like today's `card` — no reverse channel, no service auth needed. The existing
`card` → `maintenance_answer` broadcast stays for back-compat.

### 4. Feeder 2 — reverse ingress + Keycloak service auth

For proactive / streaming pushes (background job, live alert):

- New routes mirroring `blocks.py` but for remote descriptors:
  `POST /api/blocks/remote/push` · `/update` · `/remove`.
- **Auth — `require_service_principal`** (new dependency): the service-module is
  its own Keycloak client (confidential, service-account enabled, added to
  `keycloak/realm-export.json`) holding a role such as `module-push`. It obtains a
  token via the client-credentials grant and sends `Authorization: Bearer
  <token>`. The dependency validates the token via the existing Keycloak path
  (signature/issuer/expiry) and asserts the expected client + `module-push` role.
  It rejects human-user tokens and wrong-role/expired tokens.
- **Session targeting:** Atria passes `session_id` (and the block-ingress base
  URL) to the connector on every tool call; the service reuses that `session_id`
  for later proactive pushes. Atria may verify the session exists/is active before
  broadcasting.

### 5. Frontend rendering (native, reusing federation.ts)

The custom-block renderer branches on `descriptor.render`:
- `"iframe"` / absent → today's iframe path (unchanged).
- `"remote"` → a new `RemoteBlock` component: `registerRemote({name: remote_name,
  entry: remote_entry})` then `loadRemoteComponent(remote_name, component)` (the
  helpers from the dashboard work), rendered in-host with the descriptor `props`
  plus injected host props (§6). Loading/error/fallback states mirror
  `RemoteDashboard`.

### 6. Bidirectionality

The host mounts the remote component with:
- `props` — module data; updated live when an `update` arrives (React re-renders).
- `apiBase` — the block calls **its own connector** directly
  (`fetch(`${apiBase}/connector/run`, …)`), same as the dashboard.
- `sendMessage(text)` — inject a natural-language user message into the chat
  (agent-mediated action), reusing existing `AtriaBlock.sendMessage` semantics.
- `blockId` — so the component can address itself (e.g., ask the connector to
  update/remove this block).

A block acts either **directly** (connector via `apiBase`) or **through the
agent** (`sendMessage`). Live updates flow module → `POST /update` → WS
`custom_block_update` → new props.

### 7. Persistence & rehydration

A remote block persists as a `custom_block` ChatMessage carrying the descriptor.
On reload the frontend reads the descriptor and re-runs `registerRemote` +
`loadRemoteComponent`; the block returns natively. Persisted `props` are the last
state (a reloaded progress block shows its last-known value). If the remote is
unreachable on reload, `RemoteBlock` shows a graceful "component unavailable"
fallback (mirrors the connector-down card).

### 8. Security model

- Reverse ingress is Keycloak-service-auth only (§4); no anonymous pushes.
- A service can only push to a `session_id` it was handed via a tool call; Atria
  may verify the session before broadcasting.
- Federated remote code runs in the host page (not sandboxed like an iframe).
  Acceptable because **modules are first-party / trusted** (this repo's module
  trust model), exactly as the dashboard remote already is.
- Descriptor/`props` size cap reuses the existing 256 KB block cap — pass handles,
  not blobs.

## Build phasing

1. **Descriptor + WS/persistence** — `render:"remote"` variant,
   `ui_bridge.push_remote_block`, persistence carries the descriptor.
2. **Frontend `RemoteBlock`** — render path + reload rehydration (unit-testable
   with mocked federation).
3. **Feeder 1** — proxy tool honors `blocks:` in tool responses.
4. **Feeder 2** — reverse ingress + `require_service_principal` + Keycloak
   client/realm wiring + `session_id` pass-through to the connector.
5. **Bidirectionality polish** — `sendMessage`/`apiBase`/`blockId` props + live
   update flow.

## Testing

Per project rules: unit tests **and** real end-to-end simulation with a live
`OPENAI_API_KEY` (grounded/browser portions may be deferred to the user).

- **Unit:** descriptor parse/persist; `push_remote_block` broadcast envelope;
  proxy-tool `blocks:` handling; `require_service_principal` (valid / invalid /
  expired / wrong-role / user-token cases); `RemoteBlock` render + rehydrate
  (mocked federation); `render` discriminator back-compat (iframe path intact).
- **E2e:** a service pushes a live-updating block via the reverse ingress using a
  real Keycloak service-account token; the block renders natively in the chat,
  receives an update, and its `sendMessage` reaches the agent; reload rehydrates
  the block.

## Risks

- **Keycloak service-account + realm-export wiring** — the genuinely new infra;
  validate a client-credentials token end-to-end early (phase 4).
- **`require_service_principal` correctness** — must reject human-user tokens and
  wrong-role/expired service tokens; test all cases.
- **Reload rehydration** when the remote's service is down — graceful fallback
  required.
- **Session addressing for proactive push with no preceding tool call** —
  documented limitation: at least one tool call (or another session handshake)
  must establish the `session_id` before the service can push proactively.
- **React singleton / MF version** must match host↔remote (same constraint as the
  dashboard) or the block renders blank.

## Out of scope (YAGNI, for now)

- A persistent service→Atria WS/SSE channel (Approach B) — revisit only if
  HTTP-ingress push proves too chatty for sub-second streaming.
- Iframe-served-by-service blocks (Approach C).
- Untrusted/third-party module sandboxing (modules are first-party).
- A session handshake independent of tool calls (proactive push assumes a prior
  tool call established the session).
