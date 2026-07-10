# module_template SDK Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Execution mode is code-all-then-verify (user preference): implement every task in order WITHOUT running tests per-task; write each task's tests alongside its code, then run the whole suite + verification once in the final Phase V.**

**Goal:** Ship `modules/module_template/` — a runnable service-module that demonstrates every `atria_module_sdk` capability — plus wire `ctx.principal` at the host so `requires_auth` works for real, and refresh `modules/module_integration.md`.

**Architecture:** One host change (principal wiring in the tool broadcaster, fed from the session owner). One new module: a pure-Python SDK connector (fake data, no `atria` import) whose 7 tools each demo one SDK feature, plus a Module-Federation frontend (a showcase block + dashboard), Docker/compose, SKILL.md, manifest, README, and `conn.invoke`-based tests.

**Tech Stack:** Python 3.12 + `atria_module_sdk` (FastAPI/pydantic/httpx) for the module; React 18 + Vite 5 + `@module-federation/vite` for the frontend; pytest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-10-module-template-sdk-showcase-design.md`.
- **The module never imports `atria`.** `AtriaClient` (via `conn.atria_client()`) uses httpx + env only.
- Reverse-push + `push_artifact` need the Keycloak `module-push` role (the `atria-module` client already holds it); the compose snippet documents the env.
- `requires_auth` reject / `params_model` invalid → structured `{success: False, ...}`, never a 500.
- React `singleton` in the module frontend; the module's frontend `package.json` matches `maintenance_copilot`'s versions (`@module-federation/vite ^1.16.14`, `vite ^5.1.4`, `react ^18.3.1`).
- Module port is **9300**; env prefix is `MT_` (e.g. `MT_PUBLIC_BASE`).
- **SDK API (exact, already implemented):** `Connector(name, *, version="1", display_name=None, public_base_env="MODULE_PUBLIC_BASE", dashboard_dist_env="MODULE_DASHBOARD_DIST", min_core_version=None)`; `@conn.tool(name, *, description="", parameters=None, card_type=None, streaming=False, requires_auth=False, params_model=None)`; `@conn.readiness_probe`; `@conn.health_probe`; `@conn.on_startup`; `@conn.route(path, *, methods=("POST",))`; `conn.block(component, props=None, *, height="auto", title=None)`; `conn.expose_block(component_key)`; `conn.invoke(tool_name, arguments, *, principal=None, session_id=None)`; `conn.atria_client()` → `AtriaClient` with `push_block(session_id, component, props=None, *, remote_entry=None, height="auto", title=None, block_id=None) -> str`, `update_block(session_id, block_id, props)`, `remove_block(session_id, block_id)`, `push_artifact(session_id, filename, content: bytes) -> int`; `card(answer, *, card_type=None, confidence=None, review_required=False, validation_warnings=None, **extra)`. A handler may declare `principal`, `session_id`, or `**kwargs` and the SDK injects them. A streaming tool is a generator yielding `{"event": "progress"|"block"|"final", ...}` dicts.
- **Test command:** `uv run --no-sync pytest <path>`.
- **Commits:** no `Co-Authored-By: Claude` trailer.
- **`docs/` + root `tests/` are gitignored — `git add -f` for the plan and any new files under root `tests/`. The module's own `modules/module_template/backend/tests/` is under `modules/` and tracked normally.**
- **EXECUTION: code all tasks, then Phase V runs all tests + verify once.**

---

## File Structure

**Host — modified:**
- `atria/web/ws_tool_broadcaster.py` — `WebSocketToolBroadcaster` accepts + wires `principal`.
- `atria/web/agent_executor.py` — passes `principal` from `session.owner_id`.
- `atria/core/modules/remote.py` — update the stale `_make_handler` comment.
- Test: `tests/test_ctx_identity_forwarding.py` (extend).

**Module — created (all under `modules/module_template/`):**
- `backend/service.py`, `backend/app.py`, `backend/requirements.txt`, `backend/Dockerfile`, `backend/tests/test_template.py`, `backend/tests/__init__.py`
- `frontend/src/ShowcaseBlock.tsx`, `frontend/src/DashboardApp.tsx`, `frontend/vite.config.ts`, `frontend/package.json`, `frontend/tsconfig.json`, `frontend/index.html`
- `SKILL.md`, `manifest.json`, `icon.svg`, `docker-compose.snippet.yml`, `README.md`

**Docs — modified:**
- `modules/module_integration.md`.

---

# Phase H — Host: wire `ctx.principal`

### Task H1: forward the acting user to `ctx.principal`

**Files:**
- Modify: `atria/web/ws_tool_broadcaster.py`, `atria/web/agent_executor.py`, `atria/core/modules/remote.py`
- Test: `tests/test_ctx_identity_forwarding.py`

**Interfaces:**
- Consumes: `SkillToolContext.principal` (already exists); `session.owner_id`.
- Produces: `WebSocketToolBroadcaster(__init__ ..., principal: Optional[dict] = None)` sets `skill_ctx.principal = self.principal`.

- [ ] **Step 1: `ws_tool_broadcaster.py`.** Add `principal: Optional[dict] = None` to `WebSocketToolBroadcaster.__init__`'s parameters, store `self.principal = principal`, and in the `if skill_ctx is not None:` block add:

```python
            skill_ctx.principal = self.principal
```

- [ ] **Step 2: `agent_executor.py`.** At the `WebSocketToolBroadcaster(...)` construction (~line 330), pass a principal derived from the session owner. Immediately before the call, add:

```python
        _owner = getattr(session, "owner_id", "") or ""
        _principal = {"username": _owner, "email": ""} if _owner else None
```

and add `principal=_principal,` to the `WebSocketToolBroadcaster(...)` keyword arguments.

- [ ] **Step 3: `remote.py` comment.** In `_make_handler`, replace the stale comment that says agent tool calls carry no user identity with an accurate one, e.g.:

```python
        # Identity is forwarded first-party from the session: ctx.principal
        # (derived from the session owner) + ctx.session_id go to the connector
        # as X-Atria-Principal / X-Atria-Session, so a tool can gate on auth and
        # reverse-push into the right session.
```

- [ ] **Step 4: Test** — extend `tests/test_ctx_identity_forwarding.py` with a broadcaster-level assertion. Add:

```python
def test_broadcaster_wires_principal_onto_ctx():
    from atria.web.ws_tool_broadcaster import WebSocketToolBroadcaster
    from atria.core.skill_tools import SkillToolContext

    class _Reg:
        skill_ctx = SkillToolContext()

    reg = _Reg()
    WebSocketToolBroadcaster(reg, ws_manager=None, loop=None, session_id="s1",
                             principal={"username": "alice", "email": "a@x"})
    assert reg.skill_ctx.principal == {"username": "alice", "email": "a@x"}
    assert reg.skill_ctx.session_id == "s1"
```

*(If `WebSocketToolBroadcaster.__init__` requires a real `ws_manager`/`loop` type, pass `None` — the constructor only stores them; the wiring block runs regardless. If construction touches them, adapt the test to the minimal viable args by reading the `__init__`.)*

- [ ] **Step 5: Commit** — `git add atria/web/ws_tool_broadcaster.py atria/web/agent_executor.py atria/core/modules/remote.py && git add -f tests/test_ctx_identity_forwarding.py && git commit -m "feat(web): wire ctx.principal from session owner (requires_auth now works)"` — no Co-Authored-By trailer.

---

# Phase B — Module backend

### Task B1: `backend/service.py` — pure fake logic

**Files:**
- Create: `modules/module_template/backend/service.py`

**Interfaces:**
- Produces: `search(topic: str, limit: int = 3) -> dict`, `report_markdown(topic: str = "demo") -> str`, `warm_up()`, `is_warm() -> bool`. Never imports `atria`.

- [ ] **Step 1: Implement** `modules/module_template/backend/service.py`:

```python
"""Pure showcase logic for module_template — fake, in-memory, no heavy deps and
never imports ``atria``. Exists only to give the SDK connector something to return."""
from __future__ import annotations

import threading
import time

_ITEMS = [
    {"title": "Getting started", "score": 0.92},
    {"title": "Federated blocks", "score": 0.81},
    {"title": "Reverse-push", "score": 0.66},
    {"title": "Readiness gating", "score": 0.55},
    {"title": "Typed params", "score": 0.44},
]

_warm = threading.Event()


def warm_up(delay: float = 2.0) -> None:
    """Simulate a slow warm-up (index load, model download …)."""
    time.sleep(delay)
    _warm.set()


def is_warm() -> bool:
    return _warm.is_set()


def search(topic: str, limit: int = 3) -> dict:
    hits = _ITEMS[: max(0, int(limit))]
    return {"topic": topic, "count": len(hits), "results": hits}


def report_markdown(topic: str = "demo") -> str:
    lines = [f"# module_template report — {topic}", ""]
    for i, item in enumerate(_ITEMS, 1):
        lines.append(f"{i}. **{item['title']}** — score {item['score']}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 2: Commit** — `git add modules/module_template/backend/service.py && git commit -m "feat(module_template): pure showcase service logic"`.

### Task B2: `backend/app.py` — the SDK connector (all tools + lifecycle)

**Files:**
- Create: `modules/module_template/backend/app.py`

**Interfaces:**
- Consumes: `atria_module_sdk` (`Connector`, `card`); `service` (Task B1); `AtriaClientError` for the async-job guard.
- Produces: `conn` (a `Connector`), the 7 tools, lifecycle hooks, `app = conn.asgi()`.

- [ ] **Step 1: Implement** `modules/module_template/backend/app.py`:

```python
"""module_template — a runnable showcase of the atria-module-sdk surface.

Each tool demonstrates exactly one SDK capability. Pure/fake logic; never imports
``atria``. Ask the agent to "show what the module SDK can do" and it will call these.
"""
from __future__ import annotations

import logging
import threading

from pydantic import BaseModel, Field

from atria_module_sdk import Connector, card
from atria_module_sdk.client import AtriaClientError

import service

logger = logging.getLogger("module_template")

conn = Connector(
    "module_template",
    version="1",
    display_name="Module Template",
    public_base_env="MT_PUBLIC_BASE",
    dashboard_dist_env="MT_DASHBOARD_DIST",
    min_core_version="2",
)

conn.expose_block("./ShowcaseBlock")


def _block(props: dict) -> dict:
    """Federated block descriptor for this module's ShowcaseBlock component."""
    return conn.block("./ShowcaseBlock", props, title="module_template")


# --- 1. params_model: typed, validated parameters -------------------------------
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


# --- 2. card(): the generic card renderer --------------------------------------
@conn.tool("template_card", description="Demo: return a generic card().",
           parameters={"type": "object", "properties": {"note": {"type": "string"}}})
def template_card(note: str = "hello from module_template"):
    return {"output": note,
            "card": card(note, card_type="template_card", confidence=0.7,
                         validation_warnings=["this is a demo card"])}


# --- 3. conn.block(): a federated React block ----------------------------------
@conn.tool("template_block", description="Demo: render the module's own federated React block.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_block(topic: str = "demo"):
    res = service.search(topic, 3)
    return {"output": f"Rendered a federated ShowcaseBlock for {topic!r}.",
            "blocks": [_block({"kind": "block", "topic": topic, "results": res["results"]})]}


# --- 4. streaming + mid-stream block event -------------------------------------
@conn.tool("template_stream", streaming=True,
           description="Demo: a streaming tool — progress events, a mid-stream block, a final.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_stream(topic: str = "demo"):
    yield {"event": "progress", "message": "searching…", "pct": 30}
    res = service.search(topic, 3)
    yield {"event": "block", "block": _block({"kind": "stream", "topic": topic,
                                              "results": res["results"]})}
    yield {"event": "progress", "message": "finishing…", "pct": 80}
    yield {"event": "final", "success": True, "output": f"streamed {res['count']} results"}


# --- 5. requires_auth: gate on an authenticated principal ----------------------
@conn.tool("template_secure", requires_auth=True,
           description="Demo: requires_auth — only runs for an authenticated user.")
def template_secure(principal=None):
    who = getattr(principal, "username", "unknown")
    return {"output": f"authenticated call by {who}",
            "card": card(f"Secure action performed for {who}.", card_type="template_card")}


# --- 6. reverse-push: an async job pushing a live progress block ---------------
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
            import time
            time.sleep(1)
            client.update_block(sid, bid, {"kind": "job", "pct": int(i / n * 100),
                                           "done": i == n})

    threading.Thread(target=_run, args=(session_id, max(1, int(steps))),
                     name="module_template-job", daemon=True).start()
    return {"output": f"started a {steps}-step background job; watch the block update live."}


# --- 7. push_artifact: attach a report to the conversation ---------------------
@conn.tool("template_export",
           description="Demo: push_artifact — attach a generated report to the conversation.",
           parameters={"type": "object", "properties": {"topic": {"type": "string"}}})
def template_export(topic: str = "demo", session_id=None):
    if not session_id:
        return {"success": False, "output": "no session to attach an artifact to"}
    try:
        client = conn.atria_client()
        aid = client.push_artifact(session_id, f"template_report_{topic}.md",
                                   service.report_markdown(topic).encode())
    except AtriaClientError as exc:
        return {"success": False, "output": f"export failed: {exc}"}
    return {"output": f"attached report artifact #{aid} to the conversation."}


# --- lifecycle & extra endpoint ------------------------------------------------
@conn.readiness_probe
def _ready():
    return {"ready": service.is_warm(), "detail": "warming up" if not service.is_warm() else "ready"}


@conn.health_probe
def _health():
    return {"showcase": "ok"}


@conn.on_startup
def _warm_up():
    logger.info("module_template starting — warming up…")
    service.warm_up()
    logger.info("module_template warm and ready.")


@conn.route("/ping", methods=["GET"])
def ping(principal):
    return {"pong": principal.username}


app = conn.asgi()
```

- [ ] **Step 2: `backend/requirements.txt`** — create `modules/module_template/backend/requirements.txt`:

```text
# module_template ships no heavy deps — it only needs the SDK (installed separately
# in the Dockerfile from the repo root) and pydantic, which the SDK already requires.
```

- [ ] **Step 3: Commit** — `git add modules/module_template/backend/app.py modules/module_template/backend/requirements.txt && git commit -m "feat(module_template): SDK connector demoing every capability"`.

### Task B3: `backend/tests/test_template.py`

**Files:**
- Create: `modules/module_template/backend/tests/test_template.py`, `modules/module_template/backend/tests/__init__.py`

**Interfaces:**
- Consumes: `conn`, `Principal` from `atria_module_sdk`.

- [ ] **Step 1: Implement** `modules/module_template/backend/tests/test_template.py`:

```python
"""In-process tests for module_template via conn.invoke (no HTTP)."""
from __future__ import annotations

import os
import sys

# Make the backend package importable (app.py imports `service` as a top-level module).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from atria_module_sdk.connector import Principal  # noqa: E402
import app as mt  # noqa: E402


def test_typed_query_validates():
    ok = mt.conn.invoke("template_typed_query", {"topic": "blocks", "limit": 2})
    assert ok["success"] is True and ok["output"]["count"] == 2
    bad = mt.conn.invoke("template_typed_query", {"topic": "x", "limit": 99})  # >5 → invalid
    assert bad["success"] is False and "invalid arguments" in bad["output"]


def test_requires_auth_gate():
    anon = mt.conn.invoke("template_secure", {})
    assert anon["success"] is False and anon["output"] == "authentication required"
    authed = mt.conn.invoke("template_secure", {}, principal=Principal(username="alice", email="a@x"))
    assert authed["success"] is True and "alice" in authed["output"]


def test_manifest_advertises_block_and_min_core():
    from fastapi.testclient import TestClient
    os.environ["MT_PUBLIC_BASE"] = "http://localhost:9300"
    mani = TestClient(mt.conn.asgi()).get("/connector/manifest").json()
    assert mani["remote"]["exposed"]["./ShowcaseBlock"] == "./ShowcaseBlock"
    assert mani["min_core_version"] == "2"
    assert "template_card" in mani["card_types"]
```

- [ ] **Step 2:** create an empty `modules/module_template/backend/tests/__init__.py`.

- [ ] **Step 3: Commit** — `git add modules/module_template/backend/tests/ && git commit -m "test(module_template): conn.invoke tests for typed query, auth gate, manifest"`.

---

# Phase F — Module frontend (Module Federation)

### Task F1: frontend — ShowcaseBlock + Dashboard + config

**Files:**
- Create: `modules/module_template/frontend/src/ShowcaseBlock.tsx`, `.../src/DashboardApp.tsx`, `.../vite.config.ts`, `.../package.json`, `.../tsconfig.json`, `.../index.html`

- [ ] **Step 1: `src/ShowcaseBlock.tsx`** (default export, consumes props + apiBase + bridge):

```tsx
export default function ShowcaseBlock(props: any) {
  const { kind = 'block', topic = 'demo', results = [], pct, done, bridge } = props;
  return (
    <div className="bg-bg-000 border border-border-300/15 rounded-lg p-4 space-y-2">
      <div className="text-xs font-mono text-text-300">module_template · {kind}</div>
      {typeof pct === 'number' ? (
        <div>
          <div className="text-sm text-text-100 mb-1">{done ? 'Done' : `Working… ${pct}%`}</div>
          <div className="h-2 rounded bg-bg-200 overflow-hidden">
            <div className="h-full bg-accent-secondary-100" style={{ width: `${pct}%` }} />
          </div>
        </div>
      ) : (
        <>
          <div className="text-sm text-text-100">Results for <b>{topic}</b>:</div>
          <ul className="text-sm text-text-200 list-disc pl-5">
            {results.map((r: any, i: number) => (
              <li key={i}>{r.title} <span className="text-text-400">({r.score})</span></li>
            ))}
          </ul>
          <div className="flex gap-2 pt-1">
            <button className="px-2 py-1 rounded bg-bg-200 text-xs"
                    onClick={() => bridge?.toast?.('Hello from ShowcaseBlock', 'success')}>
              bridge.toast
            </button>
            <button className="px-2 py-1 rounded bg-bg-200 text-xs"
                    onClick={() => bridge?.sendMessage?.(`Tell me more about ${topic}`)}>
              bridge.sendMessage
            </button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: `src/DashboardApp.tsx`** (`{apiBase}`, lists the tools + a live ping):

```tsx
import { useEffect, useState } from 'react';

const TOOLS = [
  'template_typed_query', 'template_card', 'template_block', 'template_stream',
  'template_secure', 'template_async_job', 'template_export',
];

export default function DashboardApp({ apiBase }: { apiBase: string }) {
  const [pong, setPong] = useState<string>('…');
  useEffect(() => {
    fetch(`${apiBase}/connector/ping`).then(r => r.json())
      .then(d => setPong(d.pong ?? 'unknown')).catch(() => setPong('offline'));
  }, [apiBase]);
  return (
    <div style={{ padding: 16, fontFamily: 'system-ui' }}>
      <h2>module_template — SDK showcase</h2>
      <p>Connector: <code>{apiBase}</code> · /ping → <b>{pong}</b></p>
      <p>Ask the agent to run any of these tools to see the SDK feature it demos:</p>
      <ul>{TOOLS.map(t => <li key={t}><code>{t}</code></li>)}</ul>
    </div>
  );
}
```

- [ ] **Step 3: `vite.config.ts`:**

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';

export default defineConfig({
  plugins: [
    react(),
    federation({
      name: 'module_template',
      filename: 'remoteEntry.js',
      exposes: {
        './Dashboard': './src/DashboardApp.tsx',
        './ShowcaseBlock': './src/ShowcaseBlock.tsx',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
    }),
  ],
  build: { outDir: 'dist', target: 'esnext' },
  server: { origin: 'http://localhost:9300' },
});
```

- [ ] **Step 4: `package.json`:**

```json
{
  "name": "module-template-frontend",
  "private": true,
  "type": "module",
  "scripts": { "build": "vite build", "dev": "vite" },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1" },
  "devDependencies": {
    "@module-federation/vite": "^1.16.14",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.4.0",
    "vite": "^5.1.4"
  }
}
```

- [ ] **Step 5: `tsconfig.json`:**

```json
{
  "compilerOptions": {
    "target": "ESNext", "useDefineForClassFields": true, "lib": ["DOM", "DOM.Iterable", "ESNext"],
    "module": "ESNext", "skipLibCheck": true, "moduleResolution": "bundler",
    "resolveJsonModule": true, "isolatedModules": true, "noEmit": true, "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

- [ ] **Step 6: `index.html`:**

```html
<!doctype html>
<html><head><meta charset="UTF-8" /><title>module_template</title></head>
<body><div id="root"></div></body></html>
```

- [ ] **Step 7: Commit** — `git add modules/module_template/frontend/ && git commit -m "feat(module_template): MF frontend — ShowcaseBlock + dashboard"`.

---

# Phase M — Metadata & deploy

### Task M1: SKILL.md, manifest, icon, Dockerfile, compose, README

**Files:**
- Create: `modules/module_template/SKILL.md`, `.../manifest.json`, `.../icon.svg`, `.../backend/Dockerfile`, `.../docker-compose.snippet.yml`, `.../README.md`

- [ ] **Step 1: `SKILL.md`:**

```markdown
---
name: module_template
description: A runnable SDK showcase. Use it to demonstrate what an Atria service module can do — typed tools, generic cards, federated React blocks, streaming with live progress, auth-gated tools, background reverse-push, and artifact export. Ask it to "show the module SDK capabilities".
---

# module_template

A reference module that demonstrates every `atria_module_sdk` capability. Each tool
maps to one feature — use it to learn the SDK or as a copy-me skeleton for a new module.

## When to use

Reach for this when someone wants to see or verify what a deeply-connected Atria
module can do, or as the starting point for a new module.

- `template_typed_query` — typed, validated params (pydantic `params_model`).
- `template_card` — a generic answer card.
- `template_block` — the module's own federated React block.
- `template_stream` — streaming tool: live progress + a mid-stream block.
- `template_secure` — an auth-gated tool (only runs for an authenticated user).
- `template_async_job` — a background job that pushes a live progress block into the chat.
- `template_export` — attaches a generated report as a conversation artifact.

The dashboard lists the tools and pings the connector.
```

- [ ] **Step 2: `manifest.json`:**

```json
{
  "display_name": "Module Template",
  "tooltip": "SDK showcase — every atria-module-sdk capability",
  "icon": "icon.svg",
  "dashboard": { "title": "Module Template · SDK showcase", "default_height": 640, "badge_color": "info" },
  "remote": {
    "name": "module_template",
    "remoteEntry": "http://localhost:9300/dashboard/remoteEntry.js",
    "exposed": { "dashboard": "./Dashboard", "./ShowcaseBlock": "./ShowcaseBlock" }
  }
}
```

- [ ] **Step 3: `icon.svg`** — a minimal placeholder:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
```

- [ ] **Step 4: `backend/Dockerfile`** (multi-stage; build context is the repo root, mirroring `maintenance_copilot`):

```dockerfile
# Build context is the REPO ROOT so the image can install the shared atria-module-sdk.

# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY modules/module_template/frontend/package.json modules/module_template/frontend/package-lock.json* ./
RUN npm install
COPY modules/module_template/frontend/ ./
RUN npm run build

# --- python service stage ---
FROM python:3.12-slim
WORKDIR /app
COPY atria_module_sdk /sdk
RUN pip install --no-cache-dir /sdk
COPY modules/module_template/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt || true
COPY modules/module_template/backend/ /app
COPY --from=fe /fe/dist /app/frontend_dist
ENV PYTHONUNBUFFERED=1 \
    MT_PUBLIC_BASE=http://localhost:9300
EXPOSE 9300
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9300"]
```

- [ ] **Step 5: `docker-compose.snippet.yml`:**

```yaml
# Paste into docker-compose.yml (same network as `atria`). Build context = repo root.
  module-template:
    build:
      context: .
      dockerfile: modules/module_template/backend/Dockerfile
    ports:
      - "9300:9300"
    environment:
      # Runtime self-registration (announce) — see modules/module_integration.md §4.2
      ATRIA_URL: "http://atria:8000"
      ATRIA_MODULE_CONNECTOR_URL: "http://module-template:9300"
      ATRIA_MODULE_REMOTE_ENTRY: "http://localhost:9300/dashboard/remoteEntry.js"
      MT_PUBLIC_BASE: "http://localhost:9300"
      # Reverse-push + artifact push (module-push role):
      KEYCLOAK_TOKEN_URL: "http://keycloak:8080/realms/atria/protocol/openid-connect/token"
      ATRIA_MODULE_CLIENT_ID: "atria-module"
      ATRIA_MODULE_CLIENT_SECRET: "CHANGE-ME-IN-ENV"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:9300/connector/health')"]
      interval: 20s
      timeout: 3s
      retries: 3
```

- [ ] **Step 6: `README.md`** — map each SDK feature to the code:

```markdown
# module_template — atria-module-sdk showcase

A runnable module that exercises every SDK capability. Copy it to bootstrap a new module.

## Feature → code

- **params_model (typed params)** — `template_typed_query` + `TemplateQuery` in `backend/app.py`.
- **card()** — `template_card`.
- **conn.block() federated block** — `template_block` + `frontend/src/ShowcaseBlock.tsx`.
- **streaming + mid-stream block event** — `template_stream`.
- **requires_auth** — `template_secure` (needs an authenticated principal).
- **AtriaClient reverse-push (push/update block)** — `template_async_job` (background thread).
- **push_artifact** — `template_export`.
- **readiness_probe / health_probe / on_startup** — the lifecycle hooks in `app.py`.
- **@conn.route (generic passthrough)** — `/ping`.
- **expose_block + min_core_version** — `conn.expose_block(...)` + `Connector(min_core_version=...)`.
- **conn.invoke (in-process testing)** — `backend/tests/test_template.py`.

## Run

`atria-module dev module_template` for local iteration, or paste
`docker-compose.snippet.yml` into `docker-compose.yml` and `docker compose up -d --build module-template`.
See `modules/module_integration.md` for the full contract + required env.
```

- [ ] **Step 7: Commit** — `git add modules/module_template/SKILL.md modules/module_template/manifest.json modules/module_template/icon.svg modules/module_template/backend/Dockerfile modules/module_template/docker-compose.snippet.yml modules/module_template/README.md && git commit -m "feat(module_template): SKILL, manifest, Dockerfile, compose, README"`.

---

# Phase D — Docs

### Task D1: refresh `modules/module_integration.md`

**Files:**
- Modify: `modules/module_integration.md`

- [ ] **Step 1: Point to `module_template` as the showcase.** In the guide's intro/reference sections, add `modules/module_template/` as the exhaustive SDK-feature example (keep `maintenance_copilot` as the real-world example). Add a line near the top: "For a runnable example that exercises **every** SDK capability, see `modules/module_template/` (each tool demos one feature)."

- [ ] **Step 2: Add/refresh capability sections** so the guide matches the current SDK. Ensure these are documented with a short code example each (mirroring the module_template code):
  - `params_model` on `@conn.tool` (typed, validated params).
  - `@conn.readiness_probe` (tools hidden until ready) and how it interacts with the reconciler.
  - `requires_auth` (and the note that identity is forwarded from the session owner).
  - `conn.invoke(...)` for in-process testing.
  - `conn.expose_block(...)` + the enriched `/connector/manifest` (`card_types`, `contract_version`, `min_core_version`).
  - streaming `block` events (`yield {"event":"block", ...}`).
  - the **`AtriaClient` reverse-push channel** — `conn.atria_client()` → `push_block`/`update_block`/`remove_block`/`push_artifact`, the `module-push` role requirement, and that it needs a `session_id` captured from a tool handler.
- Keep the existing §1–§10 structure; extend §3 (backend) and §5 (chat render) and add a new subsection for the outbound `AtriaClient` channel and readiness. Do not remove correct existing content.

- [ ] **Step 3: Commit** — `git add modules/module_integration.md && git commit -m "docs(modules): refresh integration guide for full SDK surface + module_template showcase"`.

---

# Phase V — Verify (run once, at the end)

- [ ] **Step 1: Host + module Python tests**

Run: `uv run --no-sync pytest tests/test_ctx_identity_forwarding.py modules/module_template/backend/tests/ -v`
Expected: all PASS (principal wiring; typed-query validation, auth gate, manifest).

- [ ] **Step 2: Full Python suite (no regressions)**

Run: `uv run --no-sync pytest -q --ignore=tests/search/test_enterprise_acl.py --ignore=tests/search/test_stores.py`
Expected: no new failures vs baseline (pre-existing enterprise-knowledge/qdrant failures are unrelated).

- [ ] **Step 3: Lint**

Run: `uv run --no-sync ruff check atria/web/ws_tool_broadcaster.py atria/web/agent_executor.py atria/core/modules/remote.py modules/module_template/backend/`
Expected: clean.

- [ ] **Step 4: Frontend build**

Run: `cd modules/module_template/frontend && npm install && npm run build`
Expected: a clean MF build producing `dist/remoteEntry.js`.

- [ ] **Step 5: E2E (with `OPENAI_API_KEY`, per CLAUDE.md — deferred to user)**

Run the module (`atria-module dev module_template` or the compose snippet), then ask the agent to demo each capability and confirm: the typed query validates, the generic card renders, the federated ShowcaseBlock renders, the streaming tool shows live progress + a block, `template_secure` runs for an authenticated user (and rejects anonymous), `template_async_job` pushes a live-updating progress block, and `template_export` attaches a report artifact.

- [ ] **Step 6: Commit** (if any verification fixups were needed)

```bash
git add -f docs/superpowers/plans/2026-07-10-module-template-sdk-showcase.md
git add atria/ modules/module_template/
git commit -m "chore(module_template): Phase V verification fixups"
```

---

## Self-Review Notes

- **Spec coverage:** Part 1 host principal wiring → Task H1. Part 2 module: service (B1), all 7 tools + lifecycle (B2), tests (B3), frontend (F1), metadata/deploy (M1). Part 3 docs → D1. Every SDK feature in the spec maps to a tool/hook in B2 and a doc section in D1.
- **Type/name consistency:** tool names (`template_typed_query/card/block/stream/secure/async_job/export`) are identical across B2, B3, D1, F1(DashboardApp list), M1(SKILL/README). `conn.block("./ShowcaseBlock", …)` component key matches the vite `exposes` key and the manifest `remote.exposed`. `AtriaClientError` imported from `atria_module_sdk.client` (real module). `conn.invoke(...)` signature matches the SDK. `params_model=TemplateQuery` with `limit ≤ 5` matches the test's invalid case (`limit=99`).
- **Reconcile-against-reality (flagged inline):** H1 Step-4 test may need the real minimal `WebSocketToolBroadcaster.__init__` args — the implementer reads the constructor and adapts. The Dockerfile uses `|| true` on requirements install because `requirements.txt` is intentionally empty.
- **No-atria-import:** B2 imports only `atria_module_sdk` + `service` + stdlib/pydantic — no `atria`.
