# SDK Self-Registering Modules — Design

**Date:** 2026-07-10
**Status:** Approved (design), pending implementation plan
**Branch context:** builds on `feat/federated-chat-blocks` (federated chat blocks already landed the `custom_block` `render:"remote"` machinery this design depends on).

## Goal

Make an Atria service-module the deepest-integrated unit possible — its tools appear to the agent, its dashboard and chat UI render natively — while requiring **zero edits to atria source** to add one. A module is an independent microservice that lives anywhere, ships its own heavy deps in its own container, and **registers itself at runtime through the SDK**. If the module service is not running, Atria loses its tools *live*.

## Non-goals

- Persisting module registrations across Atria restarts (explicitly rejected — the running microservice is the sole source of truth; if it is down, its tools are gone).
- A marketplace / package registry for modules.
- Sandboxing federated block code (first-party trust model, unchanged).
- Changing the tool-call proxy, card broadcast, or generic passthrough wire contracts (reused as-is).

## Core decisions (from brainstorming)

1. **Registration model:** self-register at runtime via the SDK. Modules live outside the atria repo; running the container against `ATRIA_URL` is all it takes to appear.
2. **Persistence:** none. Live service-discovery. Module down → tools disappear live. `manifest.json` in-repo is no longer the source of truth for discovery.
3. **Chat render:** kill the bespoke card path. Every module output is either a **generic card** (auto, keyed on `card_type`) or a **federated React block** the module ships. `maintenance_answer` migrates to a federated block. web-ui is never edited to add a module.
4. **Liveness:** connector **push-announces once** at startup (`POST /api/modules/register`); Atria then reuses its existing pull-poll of `GET /connector/manifest` (tool-schema source of truth) + `GET /connector/health` to decide `READY` / `DOWN`.
5. **Auth:** reuse `require_service_principal` (Keycloak JWKS, already built for `blocks_remote`); add a dedicated realm role `module-register` (separate from `module-push`).

## Architecture

```
Module container (microservice, anywhere)
  │  startup: conn.asgi() startup hook → POST /api/modules/register
  │     { module, connector_url, remote_entry, api_base }  (Keycloak service principal, role module-register)
  ▼
Atria core
  ├─ Register ingress (routes/module_connector.py)
  │      → DynamicModuleRegistry.register(record@PENDING) → bump version → kick reconcile
  ├─ HealthReconciler (core/modules/watcher.py, repurposed from dir-watch)
  │      poll each registered module:
  │        GET /connector/manifest → tool schemas (source of truth); changed → update + bump version
  │        GET /connector/health   → live/stale; N consecutive fails → mark_down → tools leave catalog live
  ├─ build_remote_tool_specs (core/modules/remote.py) reads manifest from the registry record
  └─ tool call / card / block push → generic passthrough + fail-closed (unchanged)
```

Registry stays **versioned** (as today), so the prompt catalog and subagent routing rebuild automatically whenever a module appears, updates, or disappears mid-session.

## Component changes

### Atria core

- **`core/modules/registry.py` → `DynamicModuleRegistry`.** Replace boot-time directory scan with runtime registration. Record: `{module, connector_url, remote_entry, api_base, state, manifest, last_seen, fail_count}`; state machine `PENDING → READY → DOWN`. Keep the versioned API (`version()`, `list_modules()`) so downstream consumers are untouched. `list_modules()` returns only `READY` records to the agent catalog.
  - `register(announce)` — upsert `PENDING`, bump version.
  - `mark_ready(module, manifest)` / `mark_down(module)` — reconciler-driven, bump version on state change.
- **`web/routes/module_connector.py`** (extend; no new route file) — `POST /api/modules/register` gated by `require_service_principal` + role `module-register`; body `{module, connector_url, remote_entry, api_base?}`; writes to registry and kicks an immediate reconcile. Optional `POST /api/modules/deregister` for clean shutdown.
- **`core/modules/watcher.py` → HealthReconciler.** Repurpose from directory watching to polling registered connectors: `GET /connector/manifest` (schema source of truth; on change update + bump version = hot-reload of tools) + `GET /connector/health` (liveness; N fails → `mark_down`).
- **`core/modules/remote.py`.** `build_remote_tool_specs` reads the manifest from the registry record instead of a `manifest.json` file. Proxy handler, fail-closed behavior, and card broadcast unchanged.
- **Backward-compat shim.** At boot, scan any in-repo `modules/` folders and call `register()` on their behalf (migration path for `maintenance_copilot` during dev). Not a second source of truth — just auto-announces local modules.

### SDK (`atria_module_sdk`) — never imports `atria`

- **Auto-announce.** `Connector` reads `ATRIA_URL` + Keycloak client credentials from env. The `conn.asgi()` app gets a **startup hook** that POSTs `/api/modules/register` (token via client-credentials, role `module-register`) and a **shutdown hook** that best-effort POSTs `/api/modules/deregister`. No heartbeat loop in the SDK — Atria's health-poll owns liveness.
- **Manifest is derived, not committed.** `GET /connector/manifest` (already SDK-generated from decorators) becomes the single source of truth. `manifest.json` is no longer read for discovery; `atria-module new` still emits it as dev documentation/cache only.
- **Federated chat block helper.** Add `conn.block(component, props, *, remote_name, remote_entry, height, title)` alongside `card(...)`; handler returns `{"output": text, "blocks": [conn.block(...)]}`. SDK emits the `render:"remote"` descriptor matching the existing federated-chat-blocks contract.
- **CLI (`module_dev.py`).** `atria-module dev` sets `ATRIA_URL=http://localhost:8000` and announces into the dev Atria (module appears in chat without restarting Atria). Scaffold `frontend/` with an exposed chat-block component, not just a dashboard.

### web-ui (chat render migration)

- Remove bespoke `CARD_MAPPERS` from `cardRegistry.ts` — only generic card (`mapModuleCard`) + federated block (`RemoteBlock`) remain.
- Remove the `maintenance_answer` branch in `MessageList.tsx` and `MaintenanceAnswerBlock.tsx`. Module-related branches reduce to exactly two: `role === 'module_card'` (generic) and `role === 'custom_block'` with `render:"remote"` (federated). No new branch is ever needed for a new module.
- **`maintenance_copilot`** moves its answer UI into the module `frontend/` as an exposed MF component; its handler returns `blocks:[conn.block("MaintenanceAnswer", ...)]` instead of `card_type:"maintenance_answer"`. This is the end-to-end reference proof.

## Error handling & security

- **Liveness = tool visibility.** `DOWN` module → tools leave the agent catalog. A request in flight when the connector drops keeps the existing low-confidence card + LLM directive (fail-closed).
- **Auth.** Register requires a valid Keycloak service token with realm role `module-register`; missing/expired/wrong-role → 403. Reuses `require_service_principal` / JWKS validation already present.
- **URL boundary.** `connector_url` is server→server (docker-network / reachable by Atria); `remote_entry` + `api_base` are browser-facing (`localhost:<port>`). SDK splits them per the existing contract.
- **Trust.** Federated block code runs unsandboxed in the host page (same as the dashboard remote) — consistent with the federated-chat-blocks trust model.

## Testing

- **pytest:** `test_dynamic_registry` (register / mark_ready / mark_down + version bump), `test_register_route` (auth 403 vs 200, kick reconcile), `test_health_reconciler` (manifest change → hot-reload; N fails → DOWN → tools hidden), `test_remote_tool_from_registry`.
- **Vitest:** `RemoteBlock` renders; `cardRegistry` exposes only the generic path.
- **E2E (with `OPENAI_API_KEY`, per CLAUDE.md):** run Atria + `maintenance_copilot` container → announce → tool appears → agent calls it → federated block renders in chat → kill container → tool disappears live.

## Open follow-ups (not in this plan)

- Deregister-on-shutdown is best-effort; a module SIGKILL relies on health-poll to notice. Acceptable given fail-closed.
- Multi-replica of one module behind a single `connector_url` (load balancer) is out of scope; registry keys on `module` name, last announce wins.
