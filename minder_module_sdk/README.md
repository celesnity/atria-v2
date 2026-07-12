# minder-module-sdk

Build an Minder **service-module** connector without hand-rolling FastAPI. The
SDK generates the whole connector HTTP contract
([`docs/connector-contract.md`](../docs/connector-contract.md)) from decorated
handlers, so the service and the module's `manifest.json` can't drift, and
fail-closed behavior is built in.

It **never imports `minder`** — the connector runs in the module's own slim
container.

## Install

```bash
pip install minder-module-sdk          # once published
# or, from this repo, in the module's backend image:
pip install /path/to/minder_module_sdk
```

## Minimal connector

```python
# backend/app.py
from minder_module_sdk import Connector, ServiceUnavailable, card

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
