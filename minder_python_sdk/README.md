# minder-python-sdk

Build an Minder **service-module** connector without hand-rolling FastAPI. The
SDK generates the whole connector HTTP contract
([`docs/connector-contract.md`](../docs/connector-contract.md)) from decorated
handlers, so the service and the module's `manifest.json` can't drift, and
fail-closed behavior is built in.

It **never imports `minder`** — the connector runs in the module's own slim
container.

## Install

```bash
pip install minder-python-sdk          # once published
# or, from this repo, in the module's backend image:
pip install /path/to/minder_python_sdk
```

## Minimal connector

```python
# backend/app.py
from minder_python_sdk import Connector, ServiceUnavailable, card

conn = Connector("my_module", version="1")

@conn.tool(
    "my_module_query",
    description="Answer a question with grounded RAG.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    card_type="my_module_answer",
)
def query(query: str, **kwargs):
    answer = run_pipeline(query)              # your logic
    return {"output": answer, "card": card(answer["text"], confidence=answer["score"])}

@conn.health_probe
def probe():
    return {"vector_db": "ok"}

app = conn.asgi()                             # uvicorn app:app --port 9200
```

That gives you, for free:

- `GET  /connector/health` — `{ok, module, version, capabilities, sidecars}`
- `GET  /connector/manifest` — authoritative tool specs (Minder reconciles it)
- `POST /connector/tools/{name}` — never 500s the agent
- `POST /connector/tools/{name}/stream` — SSE (see streaming below)
- `/dashboard/*` — serves your built Module-Federation frontend

## Streaming

Make the handler a generator and yield `{"event": ...}` dicts:

```python
@conn.tool("slow_query", streaming=True, parameters={...})
def slow_query(query: str):
    yield {"event": "progress", "message": "retrieving…", "pct": 30}
    hits = retrieve(query)
    yield {"event": "progress", "message": "synthesizing…", "pct": 70}
    answer = synthesize(hits)
    yield {"event": "final", "success": True, "output": answer,
           "card": card(answer), "card_type": "my_module_answer"}
```

## Fail closed

Raise `ServiceUnavailable("qdrant")` when a sidecar is down — the SDK returns a
low-confidence card plus an LLM suffix that stops the model from freelancing,
instead of a 500.

## Identity & extra endpoints

Handlers can accept `principal` (the acting Minder user, forwarded as a header):

```python
@conn.tool("admin_action", parameters={...})
def admin_action(target: str, principal):
    if not principal.is_authenticated:
        return {"success": False, "output": "auth required"}
    ...

@conn.route("/signoff", methods=["POST"])
def signoff(body, principal):               # reachable via Minder's passthrough at
    return record(engineer=principal.username, **body)   # /api/modules/my_module/connector/signoff
```

## Safe to *act* through (contract v3)

v3 adds the agent-facing safety surface. All fields are optional — a v1/v2 module
upgrades with no code change, and a pre-v3 Minder core (which sends no autonomy
header) leaves every tool ungated.

**Risk gate (the moat).** Tag an action's blast radius; the SDK refuses to
auto-run anything above the caller's autonomy and returns a *decision packet* for
approval instead:

```python
@conn.tool("scrap_part", risk="high", reversible=True, undo="restore_part(part)")
def scrap_part(part: str):
    ...
# caller autonomy "low" → not executed, returns a decision_packet card
```

`risk` is `none|low|medium|high|critical`; the caller's autonomy arrives as the
`X-Minder-Autonomy` header. `@conn.read(...)` marks a pure state query (risk
`none`, never gated).

**Keep an escape route.** `reversible` says *whether* an action can be undone;
`undo` says *how* (a note or the compensating tool). Both ride every
`decision_packet`, the `/connector/manifest` tool spec, and `/connector/context`,
so the agent and the approving human always see the way back before acting.

**Operational Graph.** Register a provider so the agent can pull *linked* context
(a node + its neighbours) instead of one isolated read:

```python
@conn.graph
def graph(node, depth=1):
    return {"nodes": [...], "edges": [...]}   # around `node`, out to `depth` hops
# GET/POST /connector/graph?node=part-7&depth=2  → {nodes, edges, available}
```

With no provider the endpoint fail-closes to an empty graph (`available: false`).

**Dry-run / idempotency.** `X-Minder-Dry-Run: true` previews without executing
(passed to the handler if it accepts `dry_run`, else the SDK returns a preview
packet). `@conn.tool(..., idempotent=True)` + an `X-Minder-Request-Key` header
makes a retried call return the first result instead of acting twice.

**Structured errors.** `raise ToolError("mel_expired", "…", retryable=False)`
returns `{"success": false, "error": {code, message, retryable, details}}`.

## Accountable *after* it acts — the event envelope (the other moat)

Every non-read action auto-emits `action.invoked` / `action.completed` /
`action.failed` envelopes `{event_id, type, module, ts, source, actor, payload}`,
tagged with the acting agent (`X-Minder-Agent`) on behalf of the human — so the
Operational Graph stays ground truth even when an agent acted. Subscribe locally
with `@conn.on_event`, declare your own with `@conn.event("queue.changed",
schema=...)` and emit via `conn.emit_event(...)`, and set
`MINDER_MODULE_EMIT_EVENTS=1` to ship them to Minder's event log.

**Discovery & human loop.** `GET /connector/manifest` now advertises each tool's
`risk`/`reversible`/`idempotent` plus declared `events`; `GET /connector/context`
returns the caller's autonomy, scope, and which actions are allowed;
`GET /connector/events` is the SSE subscription; `POST /connector/decision`
applies a human approve/modify/reject (approval re-runs the action past the
gate). Build proposals with `decision_packet(action, args, assumptions=[...])`.
The `minder-ui-sdk` renders these via `<DecisionPacket>`, `useModuleEvents`, and
`useAgentContext`.

## Agent uses the real UI (declarative co-pilot)

Instead of scraping the screen, the module **declares** its navigable pages,
typed forms (fields + a per-form playbook), and controls; the agent then emits
typed **UI intents** the `minder-ui-sdk` applies to the module's real React
components. The human fills blanks and confirms — the agent proposes and points.

```python
from minder_python_sdk import navigate, fill, focus, request_confirm

conn.page("product_new", path="/products/new", label="Add product")
conn.form(
    "add_product",
    route="product_new",
    fields=[
        {"name": "sku", "type": "string", "required": True},
        {"name": "name", "type": "string", "required": True},
        {"name": "category", "type": "enum", "options": ["A", "B", "C"], "required": False},
    ],
    submit_tool="create_product",      # gated backend action run on submit
    risk="medium",
    instructions="Fill sku+name; ask the user to confirm before submitting.",
)

# drive the session's UI (agent- or module-originated):
conn.push_ui_intent(session, navigate("product_new"))
conn.push_ui_intent(session, fill("add_product", {"sku": "ABC", "name": "Widget ABC"}))
conn.push_ui_intent(session, focus("category", form="add_product"))
conn.push_ui_intent(session, request_confirm("add_product", summary="Create product ABC?"))
```

The declared surface rides in `/connector/manifest` (`ui.pages/forms/controls`)
so the agent discovers it; intents flow to the frontend over
`GET /connector/ui/intents` (SSE, per `?session=`); `MinderClient.push_ui_intent`
is the core-originated path. `submit` runs the form's `submit_tool` through the
same risk gate — so nothing irreversible happens without approval. On the
frontend, bind a real form with `useAgentForm('add_product', {value, setValue,
onSubmit})` under an `<AgentDriverProvider>`.
