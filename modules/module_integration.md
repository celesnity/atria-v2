# Building an Atria Module with the Module SDK

This is the end-to-end guide to building an Atria **service module**: a standalone
microservice whose tools appear to the agent, whose UI renders natively in the web
chat and dashboard, and whose heavy dependencies stay isolated in its own
container — **without editing a single line of Atria source (`atria/**` or
`web-ui/**`)**.

A module registers itself at **runtime**: start its container, point it at Atria,
and its tools appear live. Stop the container and its tools disappear live. Atria
never ships the module's code and never needs a redeploy to gain a new module.

The reference implementation is [`modules/maintenance_copilot/`](./maintenance_copilot).
The SDK lives in [`atria_module_sdk/`](../atria_module_sdk); it **never imports
`atria`** and runs in the module's own slim container.

For a runnable example that exercises **every** SDK capability (one tool per feature), see
[`modules/module_template/`](./module_template). Its `backend/app.py` is the
authoritative source for all code shapes in this guide; `module_template/README.md` maps
each feature to its handler.

---

## 1. Mental model — two ownership layers

A module is split into two clearly separated layers. Keep them separate:

**A. The connector (runtime-owned, lives in the module's container).**
Its existence, its **tool schemas**, and its **liveness** are discovered at
runtime. The connector announces itself to Atria on startup; Atria then
health-polls it. Tool schemas are read live from `GET /connector/manifest` — the
committed manifest is *not* the source of truth for tools. When the service is
healthy its tools are in the agent's catalog; when it dies, they leave the catalog
on the next agent turn. This is the SDK's job.

**B. The guidance folder (file-based, may live outside the Atria repo).**
A folder containing `SKILL.md` (the agent's when/how-to-use guidance and runbook)
and the *presentation* half of `manifest.json` (`display_name`, `dashboard`,
`activity` labels, `protected_paths`, `remote`). Atria reads this from the modules
root — either the repo's `modules/` dir or an external directory set via
`ATRIA_MODULES_DIR`. This is *module data*, not Atria source, so keeping a folder
still satisfies "no Atria-source edit."

> Rule of thumb: **tools & liveness are live and pushed; guidance & presentation
> are file-based and pulled.**

What Atria does for a deeply-connected module:

1. **Registers its tools as native agent tools**, proxied over HTTP, live from the
   running connector (`atria/core/modules/remote.py`).
2. **Renders its React dashboard natively** via Module Federation (no iframe,
   shares the host's React).
3. **Renders its chat output natively** — either a generic card (auto) or a
   **federated React block** the module ships (its own component in the chat).
4. **Fails closed** — a dead connector yields a structured low-confidence card
   plus an LLM directive not to freelance, never a crash.
5. **Reaches any extra endpoint** (sign-off, export, admin) through **one generic
   passthrough** — Atria core has no per-module routes.

---

## 2. Quick start

```bash
# Scaffold a full service module under the active modules directory.
atria-module new my_module --summary "What this module does." --port 9300

# Run the connector backend (uvicorn --reload) + the dashboard (vite dev) together,
# with the SDK on PYTHONPATH — edit-save-refresh, no docker rebuild. This sets
# MODULE_PUBLIC_BASE and PYTHONPATH; it does NOT set the announce env.
atria-module dev my_module
# → connector at http://localhost:9300/connector/health

# To have the local connector announce into a running Atria (so it appears in
# chat without restarting Atria), also export the announce env before `dev` —
# see §4.2:
export ATRIA_URL=http://localhost:8000
export ATRIA_MODULE_CONNECTOR_URL=http://localhost:9300
export ATRIA_MODULE_REMOTE_ENTRY=http://localhost:9300/dashboard/remoteEntry.js
```

The scaffold produces:

```text
modules/my_module/
├── SKILL.md                     # guidance: frontmatter + when/how-to-use
├── manifest.json                # presentation (display_name, dashboard, remote, protected_paths)
├── icon.svg
├── backend/
│   ├── app.py                   # SDK connector — a few decorated handlers
│   ├── service.py               # your pure logic (never imports `atria`)
│   ├── requirements.txt         # atria-module-sdk + your heavy deps
│   └── Dockerfile               # multi-stage: build frontend → slim python
├── frontend/                    # Module-Federation remote (React)
│   ├── vite.config.ts           # exposes ./Dashboard (+ your chat block components)
│   ├── package.json
│   └── src/DashboardApp.tsx
└── docker-compose.snippet.yml   # paste into docker-compose.yml to deploy
```

Then wire real logic into `backend/service.py` and paste the compose snippet.

---

## 3. The backend — `atria_module_sdk`

The SDK generates the whole connector HTTP contract from decorated handlers, so the
service can't drift from what it advertises. Import from `atria_module_sdk`:
`Connector`, `card`, `block`, `ServiceUnavailable`, `Principal`,
`unavailable_card`, `unavailable_suffix`.

### 3.1 Minimal connector

```python
# backend/app.py
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
    card_type="my_module_answer",                # names the generic-card renderer (optional)
)
def query(query: str, **kwargs) -> dict:
    answer = service.run_query(query)            # your logic
    return {"output": answer["text"], "card": card(answer["text"], confidence=answer["score"])}

@conn.health_probe
def probe() -> dict:
    return {"vector_db": "ok"}                    # sidecar reachability, surfaced in /connector/health

app = conn.asgi()                                # uvicorn app:app --port 9300
```

`Connector(name, *, version="1", display_name=None, public_base_env="MODULE_PUBLIC_BASE",
dashboard_dist_env="MODULE_DASHBOARD_DIST")`.

`conn.asgi()` builds a FastAPI app that implements the full contract and, via a
`lifespan` handler, **auto-announces to Atria on startup** and deregisters on
shutdown (see §4). It gives you for free:

- `GET  /connector/health` — `{ok, module, version, capabilities, sidecars}`
- `GET  /connector/manifest` — authoritative tool specs + remote descriptor
  (Atria reads this live; it is the source of truth for tool schemas)
- `POST /connector/tools/{name}` — invoke a tool; **never 500s the agent**
- `POST /connector/tools/{name}/stream` — SSE streaming
- `/dashboard/*` — serves your built Module-Federation frontend

### 3.2 A tool handler's return shape

Return a dict. The SDK normalizes it into the tool-response envelope
`{success, output, card, card_type, llm_suffix, blocks}`:

- `output` — what the LLM sees (string or JSON).
- `card` — a generic card dict (build it with `card(...)`), rendered by the web UI's
  generic card renderer keyed on `card_type`. Optional.
- `blocks` — a list of **federated block descriptors** (build them with `block(...)`)
  that render as native React components in the chat. Optional. See §5.
- `llm_suffix` — appended to the LLM's view of the result (e.g. a fail-closed
  directive). Optional.
- `success` — defaults to `True`.

Return a `card`, one or more `blocks`, both, or neither.

### 3.3 Streaming

Make a handler a generator, mark `streaming=True`, and yield `{"event": ...}` dicts
(`progress` / `partial` / `final`). Atria streams them to the UI; if the tool is
called on the non-stream endpoint the SDK drains it to the final result.

```python
@conn.tool("slow_query", streaming=True, parameters={...})
def slow_query(query: str):
    yield {"event": "progress", "message": "retrieving…", "pct": 30}
    hits = service.retrieve(query)
    yield {"event": "final", "success": True, "output": service.synth(hits),
           "card": card(service.synth(hits))}
```

### 3.4 Fail closed

Raise `ServiceUnavailable("qdrant")` when a sidecar is down. The SDK returns a
low-confidence card plus an LLM suffix that stops the model from freelancing,
instead of a 500. To keep your own domain-specific fail-closed card, catch your
error inside the handler and return a structured dict yourself (see
`maintenance_copilot`'s handler for the pattern).

### 3.5 Identity & extra endpoints

A handler can accept `principal` (the acting Atria user, forwarded as a header).
Register extra endpoints with `@conn.route`; they are reachable through Atria's
generic passthrough (§8):

```python
@conn.route("/signoff", methods=["POST"])
def signoff(body, principal):          # → /api/modules/my_module/connector/signoff
    return service.record(engineer=principal.username, **body)
```

### 3.6 Typed parameters with `params_model`

Pass a Pydantic `BaseModel` as `params_model` instead of hand-writing a JSON Schema.
The SDK derives the schema automatically (Pydantic v2 `model_json_schema()`) and
validates input on every call. Invalid input returns `{success: False, "output":
"invalid arguments: …"}` without reaching your handler. `params_model` and
`parameters` are mutually exclusive.

```python
from pydantic import BaseModel, Field

class TemplateQuery(BaseModel):
    topic: str = Field(description="What to search the demo corpus for.")
    limit: int = Field(default=3, ge=1, le=5, description="Max results (1–5).")

@conn.tool("template_typed_query",
           description="Demo: pydantic params_model — typed, schema-validated input.",
           params_model=TemplateQuery, card_type="template_card")
def template_typed_query(topic: str, limit: int = 3):
    res = service.search(topic, limit)
    return {"output": res, "card": card(f"Found {res['count']} results for {topic!r}.",
                                        card_type="template_card", confidence=0.9)}
```

### 3.7 Auth-gated tools with `requires_auth`

Add `requires_auth=True` to gate a tool on an authenticated principal. Atria
forwards the acting session user as `X-Atria-Principal`; anonymous callers receive
`{success: False, "output": "authentication required"}` without the handler running.

```python
@conn.tool("template_secure", requires_auth=True,
           description="Demo: requires_auth — only runs for an authenticated user.")
def template_secure(principal=None):
    who = getattr(principal, "username", "unknown")
    return {"output": f"authenticated call by {who}",
            "card": card(f"Secure action performed for {who}.", card_type="template_card")}
```

### 3.8 Readiness probe — tools hidden until ready

Decorate a zero-argument function with `@conn.readiness_probe`. It returns either a
`bool` or `{"ready": bool, …}`. While any probe reports not-ready, the connector
stays alive and answers health checks — but Atria's reconciler keeps the module's
tools **out of the agent catalog** until ready flips to `True`. Use it for connectors
that need a warm-up step (e.g. embedding a local corpus) before they can serve.

```python
@conn.readiness_probe
def _ready():
    return {"ready": service.is_warm(), "detail": "warming up" if not service.is_warm() else "ready"}

@conn.on_startup
def _warm_up():
    service.warm_up()   # runs on a daemon thread; never blocks readiness
```

`@conn.on_startup` fires each registered callback on its own daemon thread so slow
warm-up work never delays the connector from accepting health-polls. Exceptions are
logged, not fatal.

### 3.9 Streaming with a mid-stream block event

A streaming tool may `yield {"event": "block", "block": conn.block("./X", props)}`
at any point during the stream to push a federated block live into the chat, before
the final result is ready. Atria renders the block immediately and the `final` event
delivers the LLM output.

```python
@conn.tool("template_stream", streaming=True,
           description="Demo: a streaming tool — progress events, a mid-stream block, a final.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_stream(topic: str = "demo"):
    yield {"event": "progress", "message": "searching…", "pct": 30}
    res = service.search(topic, 3)
    yield {"event": "block", "block": conn.block("./ShowcaseBlock",
                                                  {"kind": "stream", "topic": topic,
                                                   "results": res["results"]})}
    yield {"event": "progress", "message": "finishing…", "pct": 80}
    yield {"event": "final", "success": True, "output": f"streamed {res['count']} results"}
```

### 3.10 In-process testing with `conn.invoke`

`conn.invoke` runs a registered tool **without HTTP** — the same validation, auth
gating, and response normalisation the endpoint applies, but in-process. Ideal for
unit tests.

```python
from atria_module_sdk.connector import Principal
import app as mt

def test_typed_query_validates():
    ok = mt.conn.invoke("template_typed_query", {"topic": "blocks", "limit": 2})
    assert ok["success"] is True

    bad = mt.conn.invoke("template_typed_query", {"topic": "x", "limit": 99})  # >5 → invalid
    assert bad["success"] is False and "invalid arguments" in bad["output"]

def test_requires_auth_gate():
    anon = mt.conn.invoke("template_secure", {})
    assert anon["output"] == "authentication required"

    authed = mt.conn.invoke("template_secure", {}, principal=Principal(username="alice", email="a@x"))
    assert authed["success"] is True and "alice" in authed["output"]
```

Signature: `conn.invoke(tool_name, arguments, *, principal=None, session_id=None) -> dict`.

---

## 4. Runtime self-registration & liveness

This is the core of the model: the module is a microservice that **announces
itself**; Atria treats the running service as the source of truth.

### 4.1 What happens

1. **Startup announce (once).** `conn.asgi()`'s lifespan handler POSTs to
   `POST /api/modules/register` with `{module, connector_url, remote_entry, api_base}`,
   authenticated by a Keycloak service token bearing the realm role
   `module-register`. Announce is best-effort — a flaky Atria never crashes your
   module. Disabled automatically when the env isn't set (e.g. TUI/headless).
2. **Health-poll (continuous).** Atria's `ConnectorReconciler` polls each
   registered connector: `GET /connector/manifest` (live tool schemas — the source
   of truth) and `GET /connector/health`. A manifest change hot-reloads the tools.
3. **Liveness = tool visibility.** While the connector is healthy its tools are in
   the agent's catalog (`PENDING → READY`). After a few consecutive health
   failures it flips to `DOWN` and its tools leave the catalog on the next agent
   turn — no persistence, no stale tools.
4. **Shutdown deregister (best-effort).** The lifespan handler POSTs
   `POST /api/modules/deregister` on clean shutdown; a hard kill is caught by the
   health-poll.

### 4.2 Environment the connector needs to announce

Set these in the module's container (the SDK reads them):

- `ATRIA_URL` — Atria's base URL the connector POSTs to (server→server).
- `ATRIA_MODULE_CONNECTOR_URL` — this connector's own URL as Atria reaches it
  (docker-network service name, e.g. `http://my-module:9300`).
- `ATRIA_MODULE_REMOTE_ENTRY` — the **browser-facing** `remoteEntry.js` URL of the
  module's federation remote (e.g. `http://localhost:9300/dashboard/remoteEntry.js`).
  `api_base` is derived from it as `remote_entry.split("/dashboard/")[0]`.
- `KEYCLOAK_TOKEN_URL`, `ATRIA_MODULE_CLIENT_ID` (default `atria-module`),
  `ATRIA_MODULE_CLIENT_SECRET` — client-credentials grant for the service token.
  If `KEYCLOAK_TOKEN_URL`/secret are absent the token step is skipped (dev/no-auth).

> **URL boundary:** `ATRIA_MODULE_CONNECTOR_URL` is server→server (Atria-in-container
> resolves it); `ATRIA_MODULE_REMOTE_ENTRY`/`api_base` are browser-facing (the user's
> browser loads them). Getting these crossed is the most common wiring bug.

### 4.3 Keycloak — one-time realm setup

Atria's realm needs (already present in `keycloak/realm-export.json`):

- a realm role `module-register`,
- a confidential service-account client `atria-module` (serviceAccountsEnabled),
  granted `module-register` via its `service-account-atria-module` user.

Give the module container the client secret. A token without `module-register` is
rejected (403); the register/deregister ingress is the only network path to
register a connector, and it is always gated.

---

## 5. Rendering in the chat — generic card vs federated block

There are exactly two ways a module's tool output renders in chat. **You never edit
`web-ui` to add a module.**

### 5.1 Generic card (simplest)

Return `card(...)` from your handler. The web UI's generic card renderer shows the
answer text, a confidence band, and validation warnings — keyed on `card_type`
(defaults to `"{module}_card"`). Good when the default card shape fits.

```python
return {"output": text, "card": card(text, confidence=0.8,
                                      validation_warnings=[], card_type="my_module_answer")}
```

`card(answer, *, card_type=None, confidence=None, review_required=False,
validation_warnings=None, **extra)` — `confidence` auto-derives a `confidence_band`
(low/medium/high); `**extra` merges arbitrary domain fields.

### 5.2 Federated block (full control — the module ships its own React UI)

When you want a bespoke, interactive card, ship a React component from the module's
own federation remote and return a **block descriptor**:

```python
from atria_module_sdk import block
import os

def _answer_block(payload: dict) -> dict:
    remote_entry = os.environ.get("ATRIA_MODULE_REMOTE_ENTRY", "")
    return block("./MyAnswer", payload,                     # component key + props
                 remote_name="my_module", remote_entry=remote_entry)

@conn.tool("my_module_query", parameters={...})
def query(query: str, **kwargs) -> dict:
    payload = service.run_query(query)
    return {"output": payload["text"], "blocks": [_answer_block(payload)]}
```

`block(component, props=None, *, remote_name, remote_entry, height="auto",
title=None)` emits `{render:"remote", remote_name, remote_entry, component, props,
api_base, height, title}`. Atria pushes it to the chat, loads the remote in-host
(no iframe, shared React), and renders it as a native message.

**The component contract.** Expose the component as the *default export*, add it to
the module `frontend/vite.config.ts` `exposes` map, and build it into the remote.
It receives:

- `...props` — exactly the `props` object you passed to `block(...)` (your raw
  payload).
- `apiBase` — the browser base for the module's own connector calls.
- `bridge` — host callbacks so the block can drive the host chat without importing
  host code:

```ts
interface BlockBridge {
  getSessionId(): string | null;
  isLoading(): boolean;
  openModuleFileTab(module: string, path: string,
    opts: { start?: number; end?: number; text?: string; nonce?: number }): void;
  prefillDraft(text: string): void;   // append to the composer draft
  sendMessage(text: string): void;    // send a follow-up into the chat
  toast(msg: string, kind: 'success' | 'error'): void;
}
```

```tsx
// frontend/src/MyAnswer.tsx
export default function MyAnswer(props: any) {
  const { answer = '', citations = [], apiBase = '', bridge } = props;
  return (
    <div>
      <p>{answer}</p>
      <button onClick={() => bridge.sendMessage('Tell me more')}>Follow up</button>
    </div>
  );
}
```

```ts
// frontend/vite.config.ts — expose it alongside the dashboard
federation({
  name: 'my_module',
  filename: 'remoteEntry.js',
  exposes: {
    './Dashboard': './src/DashboardApp.tsx',
    './MyAnswer': './src/MyAnswer.tsx',
  },
  shared: {
    react: { singleton: true, requiredVersion: '^18.3.1' },
    'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
  },
})
```

Because the block renders in-host, the host's compiled CSS is on the page — you can
use the host's utility/design-token classes directly. Any npm deps the component
needs (icon packs, etc.) must be in the module `frontend/package.json` so they build
into the remote.

> The reference `maintenance_copilot` ships a `MaintenanceAnswer` block plus four
> sub-components (citations → viewer, follow-up suggestions, clarification prefill,
> copy-to-toast) driven entirely through the `bridge`. Read it for a full example.

Persistence: pushed blocks are stored as chat messages, so they re-load after a
page refresh.

---

## 5b. Reverse-push — the `AtriaClient` outbound channel

A module can proactively push blocks and artifacts into a live session **outside a
tool call** — for example, a background job reporting progress, or a scheduled
process attaching a report. This is the reverse-push channel.

### Getting the client

```python
from atria_module_sdk.client import AtriaClientError

client = conn.atria_client()
```

`conn.atria_client()` reads the same `ATRIA_URL` the connector already uses for
announcing, and fetches a service token via the `atria-module` Keycloak client
(client-credentials grant). That client must carry the realm role `module-push`
(separate from `module-register` — see §4.3). If the env is absent or the token
request fails, `AtriaClientError` is raised.

### Pushing and updating blocks

```python
@conn.tool("template_async_job",
           description="Demo: start a background job that reverse-pushes a live progress block.",
           parameters={"type": "object", "properties": {"steps": {"type": "integer"}}})
def template_async_job(steps: int = 3, session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to push into"}

    def _run(sid: str, n: int) -> None:
        try:
            client = conn.atria_client()
        except AtriaClientError as exc:
            logger.warning("async job: atria client unavailable: %s", exc)
            return
        bid = client.push_block(sid, "./ShowcaseBlock", {"kind": "job", "pct": 0})
        for i in range(1, n + 1):
            import time; time.sleep(1)
            client.update_block(sid, bid, {"kind": "job", "pct": int(i / n * 100),
                                           "done": i == n})

    threading.Thread(target=_run, args=(session_id, max(1, int(steps))),
                     name="my_module-job", daemon=True).start()
    return {"output": f"started a {steps}-step background job; watch the block update live."}
```

The key pattern: declare `session_id` in the handler signature — Atria forwards it
via `X-Atria-Session`. The background thread captures it and uses it to target the
right conversation.

**API summary:**

- `client.push_block(session_id, component, props, *, remote_entry=None, height="auto", title=None, block_id=None) -> str` — renders a federated block in the session; returns the assigned `block_id`.
- `client.update_block(session_id, block_id, props) -> None` — updates a live block's props (e.g. progress percentage).
- `client.remove_block(session_id, block_id) -> None` — removes the block from the conversation.

All three raise `AtriaClientError` on failure — the module decides how to handle it
(log and continue, retry, etc.).

### Attaching artifacts

```python
@conn.tool("template_export",
           description="Demo: push_artifact — attach a generated report to the conversation.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_export(topic: str = "demo", session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to attach an artifact to"}
    try:
        client = conn.atria_client()
        aid = client.push_artifact(session_id, f"report_{topic}.md",
                                   service.report_markdown(topic).encode())
    except AtriaClientError as exc:
        return {"success": False, "output": f"export failed: {exc}"}
    return {"output": f"attached report artifact #{aid} to the conversation."}
```

`client.push_artifact(session_id, filename, content: bytes) -> int` — attaches a
file to the conversation; returns the artifact id. Failures raise `AtriaClientError`.

### Keycloak — the `module-push` role

The `atria-module` Keycloak client must also have the realm role `module-push`
assigned to its service account (in addition to `module-register`). The role grants
access to the `/api/blocks/remote/*` and `/api/artifacts/remote/push` endpoints.
No additional env vars are needed beyond what §4.2 already sets.

---

## 6. The dashboard — Module Federation

The exposed dashboard receives one prop, `apiBase`, and talks to its own connector
directly:

```tsx
// frontend/src/DashboardApp.tsx
export default function DashboardApp({ apiBase }: { apiBase: string }) {
  // fetch(`${apiBase}/connector/health`)
  // fetch(`${apiBase}/connector/tools/my_module_query`, {
  //   method: 'POST', body: JSON.stringify({ arguments: { query } }) })
}
```

`react`/`react-dom` must be `singleton` so the remote uses the host's React. The
multi-stage `Dockerfile` builds the frontend and copies `dist/` to the path the SDK
serves at `/dashboard/*` — exactly the `remoteEntry` URL Atria announces. The host
loads it via `web-ui/src/lib/federation.ts` + `RemoteDashboard.tsx`.

---

## 7. The guidance folder — `SKILL.md` + presentation `manifest.json`

Atria discovers a module folder under the modules root (repo `modules/` or
`ATRIA_MODULES_DIR`). It supplies the *guidance and presentation* the running
connector doesn't own:

- **`SKILL.md`** — frontmatter `name` + `description` and a when/how-to-use body.
  This is what the agent reads to decide *when* to reach for the module's tools.
- **`manifest.json` (presentation half)** — all optional:

```jsonc
{
  "display_name": "My Module",
  "tooltip": "Open the My Module module",
  "icon": "icon.svg",
  "dashboard": { "title": "My Module · dashboard", "default_height": 720, "badge_color": "info" },
  "remote": {
    "name": "my_module",
    "remoteEntry": "http://localhost:9300/dashboard/remoteEntry.js",  // browser-reachable
    "exposed": { "dashboard": "./Dashboard" }
  },
  "activity": { "default": { "running": "Working…", "done": "Done" } },
  "protected_paths": [
    { "path": "corpus", "message": "Access denied: use the my_module_query tool instead." }
  ]
}
```

`protected_paths` let a module deny the agent direct file access to its corpus
(forcing use of the tool, preserving retrieval/citations/guardrails).

Note the split: the connector's tool schemas come *live* from `/connector/manifest`;
the folder manifest carries only presentation. A `service.tools` array in the folder
manifest, if present, is documentation-only and not the source of truth.

The connector's `/connector/manifest` also advertises additional federation metadata
beyond tools. Declare federated block components with `conn.expose_block(key)` and
they appear in `remote.exposed`; the manifest also carries `card_types` (the set of
`card_type` values across all tools), `contract_version` (the SDK wire version), and
`min_core_version` (the minimum Atria build the module requires — set via
`Connector(min_core_version=…)`). Atria's reconciler reads all of these live:

```python
conn = Connector("my_module", version="1", min_core_version="2")
conn.expose_block("./MyAnswer")    # adds "./MyAnswer" to manifest remote.exposed
```

`GET /connector/manifest` response shape (relevant fields):

```jsonc
{
  "name": "my_module",
  "version": "1",
  "tools": [...],
  "remote": {
    "name": "my_module",
    "remoteEntry": "http://localhost:9300/dashboard/remoteEntry.js",
    "exposed": {"dashboard": "./Dashboard", "./MyAnswer": "./MyAnswer"}
  },
  "card_types": ["my_module_answer"],
  "contract_version": "2",
  "min_core_version": "2"
}
```

---

## 8. Extra endpoints — the generic passthrough

Atria core has **no per-module routes**. Any endpoint beyond the standard tools is
reached through one auth-checked proxy:

```
GET|POST  /api/modules/{name}/connector/{path}   → forwarded to the connector
GET       /api/modules/{name}/health             → health + capabilities
```

The acting user is forwarded as `X-Atria-Principal` (and a module-scoped secret as
`X-Atria-Module-Token` if `ATRIA_MODULE_TOKEN[_<NAME>]` is set). So a dashboard or
block button calling `/api/modules/my_module/connector/signoff` lands at your
`@conn.route("/signoff")` handler with `principal` populated — without ever touching
Atria core.

---

## 9. Deployment

Paste `docker-compose.snippet.yml` into `docker-compose.yml` (same network as
`atria`), set the env from §4.2, then:

```bash
docker compose up -d --build my-module
```

- Publish the connector's port so the **browser** can load `remoteEntry.js`.
- Add a `/connector/health` healthcheck.
- Set `MODULE_PUBLIC_BASE` so `/connector/manifest` advertises the right
  browser-facing `remoteEntry`.
- Provide `ATRIA_URL`, `ATRIA_MODULE_CONNECTOR_URL`, `ATRIA_MODULE_REMOTE_ENTRY`,
  and the Keycloak client credentials so the connector can announce.

The module appears in Atria within one health-poll cycle of coming up. No Atria
redeploy is needed to add, update, or remove a module.

---

## 10. Build checklist

1. `atria-module new my_module` — scaffold (or hand-write the tree in §2).
2. `backend/service.py` — real logic, **never imports `atria`**.
3. `backend/app.py` — SDK handlers; raise `ServiceUnavailable` when a sidecar is
   down; never 500 the agent. Return `card` and/or `blocks`.
4. Chat UI — generic `card(...)` for the default look, or ship a federated block
   (`block(...)` + a default-export React component exposed in `vite.config.ts`,
   consuming `{...props, apiBase, bridge}`).
5. `frontend/` — dashboard + any block components as MF remotes; React `singleton`;
   add npm deps the components need.
6. Guidance folder — `SKILL.md` (when/how-to-use) + `manifest.json` presentation +
   `protected_paths`. Can live in `ATRIA_MODULES_DIR` outside the repo.
7. Env — `ATRIA_URL`, `ATRIA_MODULE_CONNECTOR_URL`, `ATRIA_MODULE_REMOTE_ENTRY`,
   `MODULE_PUBLIC_BASE`, Keycloak client creds (role `module-register`).
8. Extra endpoints via `@conn.route` + the generic passthrough — never a core route.
9. `docker-compose.yml` — add the service, publish its port, healthcheck
   `/connector/health`.
10. `atria-module dev my_module` to iterate locally; deploy via the compose snippet.
11. **Optional per-tool:** `params_model=MyModel` for typed/validated parameters;
    `requires_auth=True` to gate on an authenticated principal.
12. **Optional — readiness probe:** `@conn.readiness_probe` + `@conn.on_startup` when
    the connector needs a warm-up phase before tools should enter the catalog.
13. **Optional — reverse-push channel:** `conn.atria_client()` → `push_block` /
    `update_block` / `remove_block` / `push_artifact` for background jobs that need
    to push live progress or attach files to a conversation (requires the `module-push`
    realm role on the `atria-module` Keycloak client).
14. **Optional — block federation:** `conn.expose_block("./ComponentKey")` to advertise
    extra chat-block components in `/connector/manifest`; set `min_core_version` on
    `Connector(…)` if the module requires a minimum Atria build.
15. **Testing:** use `conn.invoke(tool_name, arguments, principal=…, session_id=…)` for
    in-process unit tests — same validation and auth gating, no HTTP needed.

Once these are in place the module is deeply connected: its tools appear in the
agent's toolset live (schema-faithful, proxied over HTTP), its dashboard and chat
blocks render natively, its cards render by type — and every heavy dependency stays
isolated in the module's own container, with **zero edits to Atria source**.

---

## Reference

- SDK API: [`atria_module_sdk/README.md`](../atria_module_sdk/README.md)
- Wire contract (every endpoint, header, event): [`docs/connector-contract.md`](../docs/connector-contract.md)
- **SDK showcase (every feature, one tool each):** [`modules/module_template/`](./module_template) — for a runnable example that exercises **every** SDK capability, see this directory; `README.md` maps each feature to its handler.
- Real-world module: [`modules/maintenance_copilot/`](./maintenance_copilot) — RAG-backed module with federated block, citations, and bridged follow-ups.
- Design spec: `docs/superpowers/specs/2026-07-10-sdk-self-registering-modules-design.md`
