# SDK Self-Registering Modules — Design

**Date:** 2026-07-10
**Status:** Approved (design), pending implementation plan
**Branch context:** builds on `feat/federated-chat-blocks` (federated chat blocks already landed the `custom_block` `render:"remote"` machinery this design depends on).

## Goal

Make an Minder service-module the deepest-integrated unit possible — its tools appear to the agent, its dashboard and chat UI render natively — while requiring **zero edits to minder source** to add one. A module is an independent microservice that lives anywhere, ships its own heavy deps in its own container, and **registers itself at runtime through the SDK**. If the module service is not running, Minder loses its tools *live*.

## The two ownership layers (hybrid — settled after inspecting `maintenance_copilot`)

`maintenance_copilot` is the reference module. Inspecting it shows a module folder
carries two very different kinds of content, and they get split by owner:

- **Minder-side guidance/config (stays in the module folder):** `SKILL.md`
  (when/how-to-use + runbook for the prompt catalog and subagent routing),
  and the *presentation* half of `manifest.json` — `display_name`, `tooltip`,
  `icon`, `dashboard`, `activity` labels, `subagent`, `remote`, and
  **`protected_paths`**. The connector process does not naturally own these, so
  they remain file-based. **This folder may live outside the minder repo** via
  `MINDER_MODULES_DIR` — it is *module data*, not `minder/**` source, so keeping it
  still satisfies "no minder-source edit."
- **Runtime-owned (self-registered, live):** the connector's existence, its
  **tool schemas** (from `GET /connector/manifest`, no longer from
  `manifest.service.tools`), and **liveness**. These come from the running
  microservice via a startup announce + health-gating. Service down → tools
  disappear live.

So "no minder-source edit" means **zero edits to `minder/**` and `web-ui/**`** to
add a module. A module still owns a guidance folder; that folder can live wholly
outside the minder repo.

## Non-goals

- Persisting *runtime tool/liveness* state across Minder restarts (rejected — the running microservice is the source of truth for tools; if it is down, its tools are gone). The guidance folder is a separate, on-disk concern and is unaffected.
- Moving `SKILL.md` / `protected_paths` into `/connector/manifest` (considered and rejected — the guidance folder stays file-based).
- A marketplace / package registry for modules.
- Sandboxing federated block code (first-party trust model, unchanged).
- Changing the tool-call proxy, card broadcast, or generic passthrough wire contracts (reused as-is).

## Core decisions (from brainstorming)

1. **Registration model:** self-register at runtime via the SDK for the *connector layer*. The module's guidance folder (`SKILL.md` + presentation manifest + `protected_paths`) stays file-based and may live outside the minder repo (`MINDER_MODULES_DIR`). Running the container against `MINDER_URL` is what makes its tools appear.
2. **Tool-schema & liveness source of truth:** the running connector. `manifest.service.tools` is no longer read for schemas — tool specs come from `GET /connector/manifest`; liveness from the health-poll. No persistence of this runtime state across restarts.
3. **Chat render:** kill the bespoke card path. Every module output is either a **generic card** (auto, keyed on `card_type`) or a **federated React block** the module ships. `maintenance_answer` migrates to a federated block. web-ui is never edited to add a module.
4. **Liveness:** connector **push-announces once** at startup (`POST /api/modules/register`); Minder then reuses its existing pull-poll of `GET /connector/manifest` (tool-schema source of truth) + `GET /connector/health` to decide `READY` / `DOWN`.
5. **Auth:** reuse `require_service_principal` (Keycloak JWKS, already built for `blocks_remote`); add a dedicated realm role `module-register` (separate from `module-push`).

## Architecture

```
Module container (microservice, anywhere)
  │  startup: conn.asgi() startup hook → POST /api/modules/register
  │     { module, connector_url, remote_entry, api_base }  (Keycloak service principal, role module-register)
  ▼
Minder core
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

### Minder core

- **`core/modules/registry.py` — keep the file-based `ModuleRegistry`, add a live connector layer.** The existing folder-scan registry keeps owning the **guidance layer**: it still loads each module's `Module` (SKILL.md, `dir`, presentation `manifest`, `protected_paths`) from `resolve_modules_root()`, so `skills.py`, `prompt.py`, `subagent.py`, and `module_dashboard.py` keep reading `module.dir` unchanged. Add, alongside it, a **connector-liveness table** keyed by module name: `{connector_url, remote_entry, api_base, state, tools, last_seen, fail_count}` with a `PENDING → READY → DOWN` state machine. Bump the *same* registry `version` when a connector's state or tool set changes, so the prompt catalog / subagent routing rebuild on connector appear/disappear.
  - `register_connector(announce)` — upsert `PENDING`, bump version.
  - `mark_connector_ready(name, tools)` / `mark_connector_down(name)` — reconciler-driven, bump version on change.
  - `connector_tools(name)` — `READY` connector's live tool specs, else `[]`.
  - `live_service_modules()` — the guidance `Module`s whose connector is `READY` (what the agent tool builder consumes).
- **`web/routes/module_connector.py`** (extend; no new route file) — `POST /api/modules/register` gated by `require_service_principal` + role `module-register`; body `{module, connector_url, remote_entry, api_base?}`; writes to the connector table and kicks an immediate reconcile. Optional `POST /api/modules/deregister` for clean shutdown.
- **`core/modules/watcher.py`** — keep the filesystem watcher for the *guidance folder* (SKILL.md edits still hot-reload). **Add a separate `ConnectorReconciler`** thread that polls each registered connector: `GET /connector/manifest` (tool-schema source of truth; on change → `mark_connector_ready(name, tools)` + bump version = hot-reload) + `GET /connector/health` (liveness; N consecutive fails → `mark_connector_down`).
- **`core/modules/remote.py`.** `build_remote_tool_specs` iterates `live_service_modules()` and builds tool specs from `connector_tools(name)` (live manifest) rather than `module.manifest.service.tools`. Proxy handler, fail-closed behavior, and card broadcast unchanged.
- **Announce reconciliation with the guidance folder.** A registered connector whose name matches a known guidance `Module` binds to it (tools + liveness attach to that module). A registered connector with *no* matching folder is still allowed but logs a warning and contributes tools with no SKILL block (tools-only). `maintenance_copilot`'s folder stays; only its `manifest.service.tools` stops being the schema source.

### SDK (`minder_python_sdk`) — never imports `minder`

- **Auto-announce.** `Connector` reads `MINDER_URL` + Keycloak client credentials from env. The `conn.asgi()` app gets a **startup hook** that POSTs `/api/modules/register` (token via client-credentials, role `module-register`) and a **shutdown hook** that best-effort POSTs `/api/modules/deregister`. No heartbeat loop in the SDK — Minder's health-poll owns liveness.
- **Tool schemas are derived from the connector, not from `manifest.service.tools`.** `GET /connector/manifest` (already SDK-generated from decorators) becomes the source of truth for tool specs and liveness. The module folder's `manifest.json` keeps its *presentation* half (`display_name`, `dashboard`, `activity`, `remote`, `protected_paths`); its `service.tools` array is now optional/documentation-only. `minder-module new` still emits the full manifest.
- **Federated chat block helper.** Add `conn.block(component, props, *, remote_name, remote_entry, height, title)` alongside `card(...)`; handler returns `{"output": text, "blocks": [conn.block(...)]}`. SDK emits the `render:"remote"` descriptor matching the existing federated-chat-blocks contract.
- **CLI (`module_dev.py`).** `minder-module dev` sets `MINDER_URL=http://localhost:8000` and announces into the dev Minder (module appears in chat without restarting Minder). Scaffold `frontend/` with an exposed chat-block component, not just a dashboard.

### web-ui (chat render migration)

- Remove bespoke `CARD_MAPPERS` from `cardRegistry.ts` — only generic card (`mapModuleCard`) + federated block (`RemoteBlock`) remain.
- Remove the `maintenance_answer` branch in `MessageList.tsx` and `MaintenanceAnswerBlock.tsx`. Module-related branches reduce to exactly two: `role === 'module_card'` (generic) and `role === 'custom_block'` with `render:"remote"` (federated). No new branch is ever needed for a new module.
- **`maintenance_copilot`** moves its answer UI into the module `frontend/` as an exposed MF component; its handler returns `blocks:[conn.block("MaintenanceAnswer", ...)]` instead of `card_type:"maintenance_answer"`. This is the end-to-end reference proof.

## Error handling & security

- **Liveness = tool visibility.** `DOWN` module → tools leave the agent catalog. A request in flight when the connector drops keeps the existing low-confidence card + LLM directive (fail-closed).
- **Auth.** Register requires a valid Keycloak service token with realm role `module-register`; missing/expired/wrong-role → 403. Reuses `require_service_principal` / JWKS validation already present.
- **URL boundary.** `connector_url` is server→server (docker-network / reachable by Minder); `remote_entry` + `api_base` are browser-facing (`localhost:<port>`). SDK splits them per the existing contract.
- **Trust.** Federated block code runs unsandboxed in the host page (same as the dashboard remote) — consistent with the federated-chat-blocks trust model.

## Testing

- **pytest:** `test_connector_registry` (register_connector / mark_connector_ready / mark_connector_down + version bump; `live_service_modules` reflects state), `test_register_route` (auth 403 vs 200, kick reconcile), `test_connector_reconciler` (manifest change → hot-reload tools; N fails → DOWN → tools hidden), `test_remote_tool_from_connector` (build_remote_tool_specs uses live tools).
- **Vitest:** `RemoteBlock` renders; `cardRegistry` exposes only the generic path.
- **E2E (with `OPENAI_API_KEY`, per CLAUDE.md):** run Minder + `maintenance_copilot` container → announce → tool appears → agent calls it → federated block renders in chat → kill container → tool disappears live.

## Open follow-ups (not in this plan)

- Deregister-on-shutdown is best-effort; a module SIGKILL relies on health-poll to notice. Acceptable given fail-closed.
- Multi-replica of one module behind a single `connector_url` (load balancer) is out of scope; registry keys on `module` name, last announce wins.
