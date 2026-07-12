# Service-Module Federation — Design

**Date:** 2026-07-09
**Status:** Approved (design); implementation not started
**Pilot module:** `maintenance_copilot`
**Author:** brainstormed with Claude Code

## Summary

Extract an Minder module from the in-process module system into a self-contained,
independently-deployed **service-module**: a full-stack unit with its own backend
(FastAPI + isolated dependencies + container), its own React frontend (Module
Federation remote), and a committed docker-compose service. Minder core stops
importing the module's Python code and instead talks to it over two well-defined
seams — an HTTP **connector contract** (agent tools, dashboard actions) and
**Module Federation** (native in-host UI). The design is a *generic, reusable
service-module framework*; `maintenance_copilot` is the first migration and
`warehouse`/`rag` are expected to follow.

### Motivation

`maintenance_copilot` ships `openai`, `qdrant-client`, `neo4j`, and `chonkie`,
plus a RAG pipeline that is loaded **in-process** by Minder's tool registry (via
the module's `tools.py`). Those dependencies and that code currently live inside
the main Minder image even though they are only needed by one module. The primary
driver for this work is **heavy-dependency isolation**: get the module's deps and
pipeline code out of the Minder image, while preserving every integration surface
the module has today.

### What must be preserved

- The agent tool `maintenance_copilot_query` (same name, same behavior from the
  agent's perspective).
- The structured `maintenance_answer` UI card (answer + citation chips +
  confidence band + review gate).
- The dashboard.
- The guardrail: the agent answers maintenance questions **only** via the tool
  and never by reading `sample_manuals/` directly.
- Graceful "service unavailable" behavior when a sidecar is down (never silent
  freelancing over the corpus).

## Decisions (locked during brainstorming)

1. **Target module:** `maintenance_copilot`.
2. **Motivation:** heavy-dependency isolation (same rationale as the `asr` sidecar).
3. **Where the service lives:** *inside* `modules/<name>/` — the whole full-stack
   service is part of the module folder, not a separate top-level `services/` dir.
4. **Isolation mechanism:** **per-module container** — each service-module has its
   own `Dockerfile`; heavy deps never touch the Minder image.
5. **Orchestration:** **static compose, Minder supervises** — the service-module
   contributes a committed compose service (like `asr`); docker-compose brings it
   up; Minder discovers it via its manifest/connector URL, health-waits, and
   registers its tools. Minder does not spawn containers itself.
6. **UI integration:** the module runs its **own full React frontend**, federated
   into the Minder web UI via **Module Federation** for a native feel — **not** an
   iframe. The `maintenance_answer` card and dashboard are federated components.
7. **Scope/rollout:** full federation as the *design* target (approach A), built
   in a *backend-first phased* order so the dep-isolation win lands and is
   verifiable before the (riskier) federation frontend. Framework is **generic**
   from the start so `warehouse`/`rag` reuse it.

## Context (as-is)

- Modules are file-based, discovered from `modules/` by `ModuleRegistry`
  (`minder/core/modules/registry.py`), loaded **in-process**. A module may ship a
  `tools.py` exporting `register(ctx) -> list[ToolSpec]`; the tool registry
  (`minder/core/context_engineering/tools/registry.py`) discovers these and wires
  their handlers into the agent.
- `ToolSpec` (`minder/core/skill_tools.py`) = `{name, description, parameters,
  handler, card_path}`. `SkillToolContext` carries a mutable `broadcaster` used to
  push structured cards to the web UI.
- Module dashboards render today as **sandboxed iframes** with a postMessage
  **bridge** (`web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx`,
  `useModuleBridge.ts`) — no WebSocket, no shared store. This is the "not native"
  experience being replaced for federated modules.
- Web UI stack: React 18 + Vite 5 + Zustand. No Module Federation yet.
- An existing sidecar pattern to follow: `services/asr` (FastAPI app + Dockerfile +
  requirements + committed compose service + healthcheck).
- A work-in-progress `services/warehouse/app.py` already sketches a "connector
  contract" (`/connector/health|manifest|tools/{name}|run|summarize`) and a
  federated React remote (`remoteEntry`, `exposedModule`, `remote: true`). This
  design generalizes that contract and adds the missing Minder consumer side.

## Architecture

A **service-module** = a self-contained full-stack folder under `modules/<name>/`.
Minder core and the service communicate **only** over HTTP (connector) and Module
Federation (UI). No Python import crosses the boundary.

### 1. Folder layout

```
modules/maintenance_copilot/
  manifest.json          # gains `service:{...}` and `remote:{...}` blocks (new)
  backend/               # FastAPI connector app — owns the heavy deps
    app.py               # implements the connector contract
    pipeline/            # moved-in scripts/ (retrieval, synthesis, guardrails,
                         #   answer_schema, index_store, graph_store, etc.)
    sample_manuals/      # RAG corpus (moved here; still path-protected)
    requirements.txt     # openai, qdrant-client, neo4j, chonkie — LEAVE Minder image
    Dockerfile
  frontend/              # React Module Federation remote (own package.json)
    src/DashboardApp.tsx
    src/cards/MaintenanceAnswerCard.tsx
    vite.config.ts       # exposes ./Dashboard and ./MaintenanceAnswerCard
  compose.fragment.yml   # committed compose service definition
```

Removed from the Minder-loaded surface: the module's `tools.py`, top-level
`scripts/`, `dashboard.html`, and module-level `requirements.txt`. Minder no longer
imports the pipeline.

### 2. Connector contract (backend HTTP API)

The canonical contract every service-module implements (generalized from the
warehouse WIP):

- `GET /connector/health` → liveness `{ok, module, version}`.
- `GET /connector/manifest` →
  `{name, display_name, tools:[{name, description, parameters}],
    remote:{remoteEntry, exposed:{dashboard, cards:{...}}}, version}`.
- `POST /connector/tools/{name}` — body `{arguments}` →
  `{success, output, card?}`. `output` is the agent-facing result text; `card` is
  the structured payload the module's federated card component renders.
- `POST /connector/run` — dashboard actions `{action, args}` → result dict.

For `maintenance_copilot`, `POST /connector/tools/maintenance_copilot_query` runs
the full grounded RAG pipeline **inside the service** and returns:
- `output`: the answer text (+ the LLM-only guardrail suffix) for the agent.
- `card`: the structured `maintenance_answer` payload (answer, citations,
  confidence band, `review_required`). All `answer_schema` / `guardrails` logic
  and their deps stay service-side.

The service's pipeline continues to talk to the existing sidecars (qdrant/TEI/
copilot-llm/neo4j) exactly as today — those relationships are unchanged.

### 3. Minder consumer — remote-module registry + proxy tools

A new **remote registry path** complements the file `ModuleRegistry`:

- On startup, scan manifests for `service: true`. For each: resolve connector URL,
  **health-wait** (bounded retry with backoff), fetch `/connector/manifest`.
- Register each remote tool as a `ToolSpec` whose `handler` is a thin HTTP proxy:
  `POST {connector}/tools/{name}` with `{arguments}`; return `output` to the agent
  and forward `card` to the UI via `ctx.broadcaster` (the same broadcast path the
  in-process tool used, so the structured card still flows unchanged).
- Preserve the guardrail: `sample_manuals` stays in the protected-path set and the
  proxy tool remains the only answer path.
- **Graceful degradation:** if a connector is unreachable at startup or a call
  fails, the proxy returns the existing "service unavailable" structured card
  instead of failing Minder boot or freelancing — mirrors today's
  `ServiceUnavailableError` behavior.

### 4. Compose supervision / lifecycle

- Each service-module ships `compose.fragment.yml` (build context
  `./modules/<name>/backend`, healthcheck, `restart: unless-stopped`), included in
  the repo's top-level `docker-compose.yml` (same as `asr`).
- "Auto-start" = compose brings the container up alongside Minder. **Minder
  supervises, does not spawn**: it health-waits and registers. A doctor-style
  check reports connector reachability.
- Dev fallback (no Docker): documented `uvicorn app:app` run from `backend/` on the
  service port; Minder discovers via the same manifest URL. Not auto-managed (YAGNI).

### 5. Frontend — Module Federation (host + remote)

- **Host** (`web-ui`): add `@module-federation/vite` configured for **runtime
  dynamic remotes**. On load, Minder fetches discovered manifests and
  `registerRemotes([{name, entry: remoteEntry}])` — no build-time coupling to any
  module.
- **Remote** (module `frontend/`): own Vite + federation build exposing
  `./Dashboard` and `./MaintenanceAnswerCard`, sharing `react` / `react-dom` as
  singletons with the host.
- **Native rendering:** `ModuleDashboardView.tsx` gains a `remote` branch — when a
  module is `remote:true`, `loadRemote()` its `Dashboard` and mount it **in-host**,
  sharing the host's WebSocket + Zustand store via props/hooks; the iframe +
  `useModuleBridge` path is retired for that module.
- **Card:** the `maintenance_answer` card renders via the module's federated
  `MaintenanceAnswerCard` component (replacing a local `card_path`); the connector
  `card` payload is passed as props.

## Build phasing

Each phase is independently verifiable.

1. **Backend extraction** — move the pipeline into `backend/`, implement the
   connector contract, containerize, add the compose entry, drop the module's deps
   from the Minder image.
2. **Consumer registry + proxy tool** — remote registry path, proxy `ToolSpec`,
   card broadcast, unavailable stub. *After 1+2 the dep-isolation win is live: the
   agent tool and structured card work over HTTP; dashboard still iframe.*
3. **Federation host** — add the MF plugin + dynamic-remote runtime to `web-ui`;
   validate with a hello-world remote before touching the real dashboard.
4. **Federated dashboard + card** — build the module `frontend/` remote, wire
   in-host rendering, retire the iframe for `maintenance_copilot`.

## Testing

Per project rules: **both** unit tests and real end-to-end simulation with a live
`OPENAI_API_KEY`.

- **Unit:** connector endpoints (contract shape), proxy-tool handler (mock httpx),
  manifest fetch + tool registration, unavailable-stub path, manifest field
  parsing (`service`/`remote` blocks).
- **e2e:** `docker compose up`; real `maintenance_copilot_query` through the proxy
  against a live pipeline (qdrant/TEI/neo4j/copilot-llm); assert grounded citations,
  card renders, guardrail intact (manual reads still denied). Federated dashboard
  loads natively in the host (shared WS + store), no iframe.

## Risks

- **MF runtime dynamic remotes on Vite 5** — the genuinely new piece. Mitigation:
  validate with a hello-world remote in phase 3 before migrating the real UI.
- **React singleton mismatch** (host vs remote) → blank remote. Mitigation: pin and
  share `react`/`react-dom` versions as singletons.
- **Startup ordering** — connector not ready when Minder registers. Mitigation:
  health-wait with backoff + unavailable stub; never block boot.
- **CORS / auth** — federated FE → service (browser origin) vs proxy tool → service
  (server origin) have different origins; configure connector CORS accordingly.
- **Corpus protection regression** — ensure `sample_manuals` stays in the
  protected-path set after moving under `backend/`.

## Out of scope (YAGNI, for now)

- Minder spawning containers itself (Docker socket / generated compose).
- Auto-managed dev subprocess supervision.
- The reverse `/connector/summarize` call (maintenance_copilot's pipeline uses the
  copilot-llm sidecar directly; no reverse LLM call needed).
- Migrating `warehouse`/`rag` — the framework is built to enable them, but their
  migration is separate follow-on work.
