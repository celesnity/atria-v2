# Module Integration Guide — Building a Deeply-Connected Atria Module

This guide explains how to build an Atria **service module** that is *deeply*
connected to Atria core: its tools appear to the agent, its dashboard renders
natively in the web UI, and it ships heavy dependencies out-of-process without
polluting the Atria venv.

There are two ways to build one:

- **Recommended — SDK + scaffolder.** `atria-module new` scaffolds a complete,
  runnable module, and `atria-module dev` gives you a local hot loop. The
  backend uses `atria-module-sdk`, so you write a few decorated functions
  instead of hand-rolling FastAPI, and the service can't drift from the
  manifest. **Start here.**
- **Advanced — implement the raw contract yourself.** Any HTTP service that
  speaks the connector contract works; the SDK is optional. The full wire
  contract is in [`docs/connector-contract.md`](../docs/connector-contract.md).

The reference implementation is [`modules/maintenance_copilot/`](./maintenance_copilot).

---

## 1. What "deeply connected" means

Atria discovers a module as any folder under the modules root containing a
`SKILL.md`. A **service module** additionally declares a `service` block in
`manifest.json` pointing at its connector. Atria then:

1. **Registers the module's tools as native agent tools**, proxied over HTTP
   (`atria/core/modules/remote.py` → `build_remote_tool_specs`). Registration is
   deterministic from the committed manifest — the agent knows the tools exist
   even before the container is up.
2. **Renders the module's React dashboard natively** in the web UI via Module
   Federation (no iframe, shares the host's React).
3. **Broadcasts structured cards** to the UI, labelled by `card_type` so each
   module gets its own renderer (or a generic fallback).
4. **Fails closed** — a dead connector returns a structured low-confidence card
   plus an LLM directive not to freelance, never a crash.
5. **Reaches any extra endpoint** (sign-off, export, admin) through **one
   generic passthrough** — core has no per-module routes.

Key rule throughout: **the backend never imports `atria`.** It runs in its own
slim container with only its own dependencies.

---

## 2. Quick start (recommended path)

```bash
# Scaffold a full service module under the active modules directory.
atria-module new my_module --summary "What this module does." --port 9300

# Run the connector backend (uvicorn --reload) + dashboard (vite dev) together,
# with the SDK on PYTHONPATH — edit-save-refresh, no docker rebuild.
atria-module dev my_module
# → connector at http://localhost:9300/connector/health
```

The scaffold produces:

```text
modules/my_module/
├── SKILL.md                     # frontmatter + when/how-to-use
├── manifest.json                # service + remote blocks, prefilled
├── icon.svg
├── backend/
│   ├── app.py                   # SDK connector — a few decorated handlers
│   ├── service.py               # your pure logic (no `atria` import)
│   ├── requirements.txt         # atria-module-sdk + your heavy deps
│   └── Dockerfile               # multi-stage: build frontend → slim python
├── frontend/                    # Module-Federation remote (React dashboard)
│   ├── vite.config.ts
│   ├── package.json
│   └── src/DashboardApp.tsx
└── docker-compose.snippet.yml   # paste into docker-compose.yml to deploy
```

Then wire real logic into `backend/service.py`, and paste
`docker-compose.snippet.yml` into `docker-compose.yml`.

---

## 3. The backend — `atria-module-sdk`

The SDK ([`atria_module_sdk/`](../atria_module_sdk)) generates the whole
connector contract from decorated handlers. A minimal `backend/app.py`:

```python
from atria_module_sdk import Connector, ServiceUnavailable, card
import service                                   # backend/service.py — pure logic

conn = Connector("my_module", version="1")

@conn.tool(
    "my_module_query",
    description="Answer a question with grounded RAG.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    card_type="my_module_answer",                # names the UI renderer
)
def query(query: str, **kwargs):
    answer = service.run_query(query)            # your logic
    return {"output": answer, "card": card(answer)}

@conn.health_probe
def probe():
    return {"vector_db": "ok"}

app = conn.asgi()                                # uvicorn app:app --port 9300
```

That gives you, for free:

- `GET  /connector/health` — `{ok, module, version, capabilities, sidecars}`
- `GET  /connector/manifest` — authoritative tool specs (Atria reconciles them)
- `POST /connector/tools/{name}` — never 500s the agent
- `POST /connector/tools/{name}/stream` — SSE (streaming, below)
- `/dashboard/*` — serves your built Module-Federation frontend

**Fail closed:** raise `ServiceUnavailable("qdrant")` from a handler when a
sidecar is down — the SDK returns a low-confidence card + an LLM suffix that
stops the model from freelancing, instead of a 500.

**Streaming:** make a handler a generator, mark `streaming=True`, and yield
`{"event": ...}` dicts (`progress` / `partial` / `final`). Atria streams them
to the UI; if the tool is called on the non-stream endpoint the SDK drains it
to the final result automatically.

```python
@conn.tool("slow_query", streaming=True, parameters={...})
def slow_query(query: str):
    yield {"event": "progress", "message": "retrieving…", "pct": 30}
    hits = retrieve(query)
    yield {"event": "final", "success": True, "output": synth(hits),
           "card": card(synth(hits)), "card_type": "my_module_answer"}
```

**Identity & extra endpoints:** a handler can accept `principal` (the acting
Atria user, forwarded as a header). Register extra endpoints with `@conn.route`;
they're reachable through Atria's generic passthrough (§6):

```python
@conn.route("/signoff", methods=["POST"])
def signoff(body, principal):          # → /api/modules/my_module/connector/signoff
    return record(engineer=principal.username, **body)
```

See [`atria_module_sdk/README.md`](../atria_module_sdk/README.md) for the full API.

---

## 4. The manifest — `service` + `remote`

Tool registration is deterministic from the committed manifest (the agent knows
the tools before the container starts). v2 fields are marked; all are optional.

```jsonc
{
  "display_name": "My Module",
  "tooltip": "Open the My Module module",
  "icon": "icon.svg",
  "dashboard": { "title": "My Module · dashboard", "default_height": 720, "badge_color": "info" },

  "service": {
    "connector_url": "http://my-module:9300",   // docker-network service name
    "health_path": "/connector/health",
    "streaming": false,                          // v2: tools may use /stream
    "min_core_version": "2",                     // v2: optional
    "tools": [
      {
        "name": "my_module_query",
        "description": "Answer a question and render it as a card.",
        "parameters": { "type": "object",
          "properties": { "query": { "type": "string" } }, "required": ["query"] }
      }
    ]
  },

  "remote": {
    "name": "my_module",
    "remoteEntry": "http://localhost:9300/dashboard/remoteEntry.js",  // browser-reachable
    "exposed": { "dashboard": "./Dashboard" }
  }
}
```

Note the URL split: `connector_url` uses the **docker-network service name**
(Atria-in-container resolves it); `remoteEntry` uses a **browser-reachable**
URL (the browser loads it). The SDK keeps the manifest's tool schemas honest —
Atria reconciles them against `GET /connector/manifest` when
`ATRIA_RECONCILE_CONNECTORS=1` and warns on drift.

---

## 5. The dashboard — Module Federation

The exposed component receives one prop, `apiBase` (the connector's public base),
and talks to its own connector directly for data:

```tsx
export default function DashboardApp({ apiBase }: { apiBase: string }) {
  // fetch(`${apiBase}/connector/health`)
  // fetch(`${apiBase}/connector/tools/my_module_query`, {
  //   method: 'POST', body: JSON.stringify({ arguments: { query } }) })
}
```

`react`/`react-dom` must be `singleton` in `vite.config.ts` so the remote uses
the host's React. The multi-stage `Dockerfile` builds the frontend and copies
`dist/` → `/app/frontend_dist`, which the SDK serves at `/dashboard/*` — exactly
the `remoteEntry` URL in the manifest. The host loads it via
`web-ui/src/lib/federation.ts` + `RemoteDashboard.tsx`.

Cards your tools broadcast are rendered by the web UI keyed on `card_type`:
a registered renderer if one exists (e.g. `maintenance_answer`), else a generic
card renderer for `"{module}_card"`.

---

## 6. Extra endpoints — the generic passthrough

Core has **no per-module routes**. Any endpoint beyond the standard tools is
reached through one auth-checked proxy:

```
GET|POST  /api/modules/{name}/connector/{path}   → forwarded to the connector
GET       /api/modules/{name}/health             → health + capabilities
```

The acting user is forwarded to the connector as `X-Atria-Principal` (and a
module-scoped secret as `X-Atria-Module-Token` if `ATRIA_MODULE_TOKEN[_<NAME>]`
is set). So a dashboard button calling `/api/modules/my_module/connector/signoff`
lands at your `@conn.route("/signoff")` handler with `principal` populated —
without ever touching Atria core.

---

## 7. Deployment

Paste `docker-compose.snippet.yml` into `docker-compose.yml` (same network as
`atria`), then:

```bash
docker compose up -d --build my-module
```

Publish the connector's port so the **browser** can load `remoteEntry.js`; add a
`/connector/health` healthcheck. The `atria` service mounts `./modules`, so it
reads your `manifest.json` and registers the proxy tools automatically.

---

## 8. Build checklist

1. `atria-module new my_module` — scaffold (or hand-write the tree in §2).
2. `backend/service.py` — real logic, **no `atria` import**.
3. `backend/app.py` — SDK handlers; raise `ServiceUnavailable` when a sidecar is
   down; never 500 the agent.
4. `manifest.json` — `service` block (docker-network `connector_url`, tool
   schemas) + `remote` block (browser-reachable `remoteEntry`).
5. Dashboard component takes `{ apiBase }`; React is `singleton`.
6. Extra endpoints via `@conn.route` + the generic passthrough — never a core
   route.
7. `docker-compose.yml` — add the service, publish its port, health-check
   `/connector/health`.
8. `atria-module dev my_module` to iterate locally; deploy via the compose
   snippet.

Once these are in place the module is deeply connected: its tools appear in the
agent's toolset (schema-faithful, proxied over HTTP), its dashboard renders
natively, its cards render by type, and all of its heavy dependencies stay
isolated in the module's own container.

---

## Reference

- Wire contract (every endpoint, header, event): [`docs/connector-contract.md`](../docs/connector-contract.md)
- SDK API: [`atria_module_sdk/README.md`](../atria_module_sdk/README.md)
- Reference module: [`modules/maintenance_copilot/`](./maintenance_copilot)
