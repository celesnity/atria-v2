# Federated Chat Blocks Implementation Plan

> **For agentic workers:** Execution mode for THIS plan is **code-all-then-verify** (user preference): implement every task in order WITHOUT running tests per-task, then run the whole test suite + verification once in the final **Phase V**. The test code in each task is written alongside the implementation but executed in Phase V. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let a service-module push its own React components into the Minder chat, rendered natively in-host via Module Federation — both as an agent tool-call response and via a Keycloak-authenticated proactive reverse-push — live-updatable and bidirectional.

**Architecture:** Add one block *variant* (`render:"remote"`) that carries a federation descriptor `{remote_name, remote_entry, component, props}` through the existing `custom_block` WS + persistence machinery. Two feeders write it: the proxy tool (in-process, tool response) and a new Keycloak-service-auth reverse ingress (`POST /api/blocks/remote/{push,update,remove}`). The frontend branches on `render` and renders remote blocks with the `loadRemoteComponent` helper already built for the dashboard.

**Tech Stack:** Python 3.12 + FastAPI + PyJWT (Keycloak JWKS validation, already present); React 18 + Vite 5 + `@module-federation/runtime`; pytest + Vitest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-10-federated-chat-blocks-design.md`.
- **Reuse, don't fork:** extend the existing `custom_block` / `custom_block_update` / `custom_block_remove` WS types and `custom_block` ChatMessage persistence — do NOT invent parallel WS types. Iframe blocks (`render` absent or `"iframe"`) must keep working unchanged.
- **Descriptor shape (canonical, used everywhere):** `{block_id, render:"remote", module, remote_name, remote_entry, component, props, api_base, title, height, persist}`.
- **URL boundary:** `remote_entry`/`api_base` are BROWSER-facing (`localhost:<port>`); the connector `connector_url` (server→server) is unrelated here. `api_base` = `remote_entry.split('/dashboard/')[0]`.
- **Keycloak service auth:** the reverse ingress is gated by `require_service_principal` — a valid Keycloak token carrying the realm role `module-push`. Human-user tokens (no `module-push`) and expired/wrong-role tokens are rejected. Role constant: `MODULE_PUSH_ROLE = "module-push"`.
- **First-party trust:** federated remote block code runs unsandboxed in the host page (same as the dashboard remote) — acceptable per the module trust model.
- **Frontend build:** npm (`make build-ui` → `npm ci`/`npm run build`), not pnpm. React/react-dom shared singletons `^18.3.1`; `@module-federation/*` versions match `web-ui`.
- **Test command:** `uv run --no-sync pytest <path>` (never bare `pytest`); `npx vitest run <path>` / `npm run build` for web-ui.
- **Commits:** no `Co-Authored-By: Claude` trailer.
- **EXECUTION: code all tasks, then Phase V runs all tests + verify once.**

---

## File Structure

**Backend — created:**
- `minder/web/dependencies/service_auth.py` — `require_service_principal` (Keycloak service-account gate).
- `minder/web/routes/blocks_remote.py` — `POST /api/blocks/remote/{push,update,remove}`.
- `tests/test_push_remote_block.py`, `tests/test_service_auth.py`, `tests/test_blocks_remote_route.py`, `tests/test_proxy_tool_blocks.py`.

**Backend — modified:**
- `minder/web/ui_bridge.py` — add `push_remote_block(...)`.
- `minder/core/modules/remote.py` — proxy handler honors `blocks:` in tool responses + passes `session_id`/ingress to the connector.
- `minder/web/server.py` — register the `blocks_remote` router.
- `keycloak/realm-export.json` — add a confidential `minder-module` client (service accounts) + realm role `module-push`.

**Frontend — created:**
- `web-ui/src/components/Chat/RemoteBlock.tsx` — native federated block renderer.
- `web-ui/src/components/Chat/RemoteBlock.test.tsx`.

**Frontend — modified:**
- `web-ui/src/types/index.ts` — chat-message remote-descriptor fields.
- `web-ui/src/stores/chat.ts` — carry the descriptor on `custom_block` (WS + persistence rehydrate); updates/removes reused.
- `web-ui/src/components/Chat/MessageList.tsx` — branch to `RemoteBlock` for remote descriptors.

---

# Phase 1 — Backend

### Task 1: `ui_bridge.push_remote_block`

**Files:**
- Modify: `minder/web/ui_bridge.py`
- Test: `tests/test_push_remote_block.py`

**Interfaces:**
- Produces: `push_remote_block(*, module, remote_name, remote_entry, component, props=None, block_id=None, api_base=None, title=None, height="auto", session_id=None, persist=True) -> str`. Broadcasts a `WSMessageType.CUSTOM_BLOCK` envelope whose `data` carries `render:"remote"` + the descriptor, and persists the same payload as a `custom_block` message (reusing `_persist_block`). Returns `block_id`.

- [ ] **Step 1: Implement `push_remote_block`** (add after `push_block` in `minder/web/ui_bridge.py`):

```python
def push_remote_block(
    *,
    module: str,
    remote_name: str,
    remote_entry: str,
    component: str,
    props: Optional[Dict[str, Any]] = None,
    block_id: Optional[str] = None,
    api_base: Optional[str] = None,
    height: Any = "auto",
    title: Optional[str] = None,
    session_id: Optional[str] = None,
    persist: bool = True,
) -> str:
    """Render a module's federated React component (``component`` exposed by its
    Module Federation remote) natively in the chat — no iframe. Mirrors
    ``push_block`` but carries a ``render="remote"`` descriptor instead of an
    iframe ``src``.
    """
    bid = block_id or secrets.token_hex(8)
    safe_props = _serialize_props(props)
    api = api_base or (remote_entry.split("/dashboard/")[0] if "/dashboard/" in remote_entry else "")
    payload: Dict[str, Any] = {
        "block_id": bid,
        "render": "remote",
        "module": module,
        "remote_name": remote_name,
        "remote_entry": remote_entry,
        "component": component,
        "api_base": api,
        "props": safe_props,
        "height": height,
        "title": title,
    }
    envelope = {
        "type": WSMessageType.CUSTOM_BLOCK,
        "data": {**payload, "session_id": session_id},
    }
    if not _publish_or_broadcast(session_id, envelope):
        raise RuntimeError("no active session")
    if persist:
        _persist_block(session_id, payload, cb=get_current_ui_callback(session_id))
    return bid


def current_session_id() -> Optional[str]:
    """Best-effort: the session id of the active agent turn (from the contextvar)."""
    cb = get_current_ui_callback(None)
    return getattr(cb, "session_id", None)
```

- [ ] **Step 2: Tests (written now; run in Phase V)** — create `tests/test_push_remote_block.py`:

```python
"""push_remote_block broadcasts a render:remote descriptor + persists it."""
from __future__ import annotations

from minder.web import ui_bridge
from minder.web.protocol import WSMessageType


def test_push_remote_block_broadcasts_descriptor(monkeypatch):
    sent = {}
    monkeypatch.setattr(ui_bridge, "_publish_or_broadcast",
                        lambda sid, env: (sent.update(env) or True))
    persisted = {}
    monkeypatch.setattr(ui_bridge, "_persist_block",
                        lambda sid, meta, cb=None: persisted.update(meta))
    monkeypatch.setattr(ui_bridge, "get_current_ui_callback", lambda sid=None: None)

    bid = ui_bridge.push_remote_block(
        module="maintenance_copilot", remote_name="maintenance_copilot",
        remote_entry="http://localhost:9200/dashboard/remoteEntry.js",
        component="./AlertsBlock", props={"n": 3}, session_id="s1",
    )
    assert sent["type"] == WSMessageType.CUSTOM_BLOCK
    d = sent["data"]
    assert d["render"] == "remote"
    assert d["remote_name"] == "maintenance_copilot"
    assert d["component"] == "./AlertsBlock"
    assert d["api_base"] == "http://localhost:9200"      # derived
    assert d["block_id"] == bid
    assert persisted["render"] == "remote" and persisted["props"] == {"n": 3}


def test_push_remote_block_no_session_raises(monkeypatch):
    monkeypatch.setattr(ui_bridge, "_publish_or_broadcast", lambda sid, env: False)
    monkeypatch.setattr(ui_bridge, "get_current_ui_callback", lambda sid=None: None)
    import pytest
    with pytest.raises(RuntimeError):
        ui_bridge.push_remote_block(module="m", remote_name="m",
            remote_entry="http://x/dashboard/remoteEntry.js", component="./B")
```

- [ ] **Step 3: Commit**

```bash
git add minder/web/ui_bridge.py tests/test_push_remote_block.py
git commit -m "feat(ui_bridge): push_remote_block — native federated chat blocks"
```

---

### Task 2: `require_service_principal` (Keycloak service-account gate)

**Files:**
- Create: `minder/web/dependencies/service_auth.py`
- Test: `tests/test_service_auth.py`

**Interfaces:**
- Consumes: `minder.web.state.get_state().keycloak.validator.validate(token) -> claims: dict` (existing Keycloak JWKS validator).
- Produces: `async require_service_principal(request: Request) -> dict` returning `{"client_id": str|None, "roles": list[str]}`; raises `HTTPException(401)` on missing/invalid token, `403` when the realm role `module-push` is absent, `503` when Keycloak isn't configured. Constant `MODULE_PUSH_ROLE = "module-push"`.

- [ ] **Step 1: Implement** — create `minder/web/dependencies/service_auth.py`:

```python
"""Service-principal auth: a Keycloak service-account token bearing the
``module-push`` realm role. Distinct from human-user login
(``require_authenticated_user``) — used to gate the module reverse-push ingress.
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status

from minder.web.state import get_state

MODULE_PUSH_ROLE = "module-push"


async def require_service_principal(request: Request) -> dict:
    state = get_state()
    services = getattr(state, "keycloak", None)
    if services is None or getattr(services, "validator", None) is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "service auth not configured")

    auth = request.headers.get("Authorization", "")
    token = auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        claims = services.validator.validate(token)
    except Exception as exc:  # noqa: BLE001 — any validation failure is a 401
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    roles = list((claims.get("realm_access") or {}).get("roles") or [])
    if MODULE_PUSH_ROLE not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing {MODULE_PUSH_ROLE} role")
    return {"client_id": claims.get("azp") or claims.get("clientId"), "roles": roles}
```

- [ ] **Step 2: Tests** — create `tests/test_service_auth.py`:

```python
"""require_service_principal: accepts module-push service tokens, rejects the rest."""
from __future__ import annotations

import types

import pytest
from fastapi import HTTPException

from minder.web.dependencies import service_auth


def _request(auth_header: str | None):
    headers = {"Authorization": auth_header} if auth_header else {}
    return types.SimpleNamespace(headers=headers)


def _patch_state(monkeypatch, validate):
    fake = types.SimpleNamespace(keycloak=types.SimpleNamespace(
        validator=types.SimpleNamespace(validate=validate)))
    monkeypatch.setattr(service_auth, "get_state", lambda: fake)


@pytest.mark.asyncio
async def test_accepts_service_token_with_role(monkeypatch):
    _patch_state(monkeypatch, lambda t: {"azp": "minder-module",
                                         "realm_access": {"roles": ["module-push"]}})
    out = await service_auth.require_service_principal(_request("Bearer good"))
    assert out["client_id"] == "minder-module"
    assert "module-push" in out["roles"]


@pytest.mark.asyncio
async def test_rejects_user_token_without_role(monkeypatch):
    _patch_state(monkeypatch, lambda t: {"preferred_username": "alice",
                                         "realm_access": {"roles": ["user"]}})
    with pytest.raises(HTTPException) as ei:
        await service_auth.require_service_principal(_request("Bearer usertok"))
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_rejects_invalid_token(monkeypatch):
    def boom(t):
        raise ValueError("bad sig")
    _patch_state(monkeypatch, boom)
    with pytest.raises(HTTPException) as ei:
        await service_auth.require_service_principal(_request("Bearer bad"))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_rejects_missing_token(monkeypatch):
    _patch_state(monkeypatch, lambda t: {})
    with pytest.raises(HTTPException) as ei:
        await service_auth.require_service_principal(_request(None))
    assert ei.value.status_code == 401
```

(Confirm `pytest-asyncio` is available — the repo already has async tests; if the marker style differs, match the existing convention, e.g. `anyio`. Grep an existing `tests/` async test for the marker.)

- [ ] **Step 3: Commit**

```bash
git add minder/web/dependencies/service_auth.py tests/test_service_auth.py
git commit -m "feat(auth): require_service_principal — Keycloak module-push service gate"
```

---

### Task 3: Reverse ingress `POST /api/blocks/remote/{push,update,remove}`

**Files:**
- Create: `minder/web/routes/blocks_remote.py`
- Modify: `minder/web/server.py` (register router)
- Test: `tests/test_blocks_remote_route.py`

**Interfaces:**
- Consumes: `ui_bridge.push_remote_block`, `ui_bridge.update_block`, `ui_bridge.remove_block`; `require_service_principal`.
- Produces: `POST /api/blocks/remote/push` → `{"block_id": str}`; `/update` (204); `/remove` (204). All require a service principal and a `session_id`.

- [ ] **Step 1: Implement** — create `minder/web/routes/blocks_remote.py`:

```python
"""Reverse-push ingress for service-modules: mount a federated component in the
chat, or update/remove it. Gated by a Keycloak service principal (module-push).
The subprocess/iframe equivalent lives in ``routes/blocks.py``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from minder.web import ui_bridge
from minder.web.dependencies.service_auth import require_service_principal

router = APIRouter(prefix="/api/blocks/remote", tags=["blocks"],
                   dependencies=[Depends(require_service_principal)])


class PushRemoteBody(BaseModel):
    session_id: str = Field(min_length=1)
    module: str = Field(min_length=1)
    remote_name: str = Field(min_length=1)
    remote_entry: str = Field(min_length=1)
    component: str = Field(min_length=1)
    props: Optional[Dict[str, Any]] = None
    block_id: Optional[str] = None
    api_base: Optional[str] = None
    height: Any = "auto"
    title: Optional[str] = None
    persist: bool = True


class UpdateBody(BaseModel):
    session_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)
    props: Dict[str, Any]


class RemoveBody(BaseModel):
    session_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)


@router.post("/push")
def push(body: PushRemoteBody) -> Dict[str, str]:
    try:
        bid = ui_bridge.push_remote_block(
            module=body.module, remote_name=body.remote_name,
            remote_entry=body.remote_entry, component=body.component,
            props=body.props, block_id=body.block_id, api_base=body.api_base,
            height=body.height, title=body.title,
            session_id=body.session_id, persist=body.persist,
        )
    except RuntimeError as exc:  # no active session
        raise HTTPException(404, str(exc)) from exc
    return {"block_id": bid}


@router.post("/update", status_code=204)
def update(body: UpdateBody) -> None:
    try:
        ui_bridge.update_block(body.block_id, body.props, session_id=body.session_id)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/remove", status_code=204)
def remove(body: RemoveBody) -> None:
    try:
        ui_bridge.remove_block(body.block_id, session_id=body.session_id)
    except RuntimeError as exc:
        raise HTTPException(404, str(exc)) from exc
```

- [ ] **Step 2: Register the router** in `minder/web/server.py` — next to where the existing `blocks` router is included (grep `include_router` + `blocks`), add:

```python
    from minder.web.routes.blocks_remote import router as blocks_remote_router
    app.include_router(blocks_remote_router)
```
(Match the file's existing import/registration style — some routers are imported at top, some inline. Follow whichever the `blocks` router uses.)

- [ ] **Step 3: Tests** — create `tests/test_blocks_remote_route.py`:

```python
"""The remote-block ingress calls ui_bridge and is service-auth gated."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from minder.web.routes import blocks_remote
from minder.web.dependencies.service_auth import require_service_principal


def _client(monkeypatch):
    app = FastAPI()
    # bypass Keycloak in the unit test — auth itself is covered by test_service_auth
    app.dependency_overrides[require_service_principal] = lambda: {"client_id": "minder-module", "roles": ["module-push"]}
    app.include_router(blocks_remote.router)
    return TestClient(app)


def test_push_calls_ui_bridge(monkeypatch):
    seen = {}
    monkeypatch.setattr(blocks_remote.ui_bridge, "push_remote_block",
                        lambda **k: (seen.update(k) or "bid-1"))
    client = _client(monkeypatch)
    r = client.post("/api/blocks/remote/push", json={
        "session_id": "s1", "module": "maintenance_copilot",
        "remote_name": "maintenance_copilot",
        "remote_entry": "http://localhost:9200/dashboard/remoteEntry.js",
        "component": "./AlertsBlock", "props": {"n": 1},
    })
    assert r.status_code == 200 and r.json()["block_id"] == "bid-1"
    assert seen["session_id"] == "s1" and seen["component"] == "./AlertsBlock"


def test_update_and_remove(monkeypatch):
    calls = []
    monkeypatch.setattr(blocks_remote.ui_bridge, "update_block",
                        lambda bid, props, session_id=None: calls.append(("u", bid)))
    monkeypatch.setattr(blocks_remote.ui_bridge, "remove_block",
                        lambda bid, session_id=None: calls.append(("r", bid)))
    client = _client(monkeypatch)
    assert client.post("/api/blocks/remote/update",
                       json={"session_id": "s1", "block_id": "b1", "props": {"x": 2}}).status_code == 204
    assert client.post("/api/blocks/remote/remove",
                       json={"session_id": "s1", "block_id": "b1"}).status_code == 204
    assert calls == [("u", "b1"), ("r", "b1")]
```

- [ ] **Step 4: Commit**

```bash
git add minder/web/routes/blocks_remote.py minder/web/server.py tests/test_blocks_remote_route.py
git commit -m "feat(blocks): reverse ingress for federated chat blocks (service-auth gated)"
```

---

### Task 4: Feeder 1 — proxy tool honors `blocks:` + hands the service the session context

**Files:**
- Modify: `minder/core/modules/remote.py`
- Test: `tests/test_proxy_tool_blocks.py`

**Interfaces:**
- Consumes: `ui_bridge.push_remote_block`, `ui_bridge.current_session_id` (Task 1); the connector tool response may include `blocks: [descriptor…]`.
- Produces: the proxy handler, on a tool response containing `blocks`, pushes each as a remote block (broadcast + persist). It also injects an `_minder` context object into the outgoing tool `arguments` so the service can push proactively later:
  `arguments["_minder"] = {"session_id": <current>, "block_ingress": "<minder_base>/api/blocks/remote"}`. The Minder base comes from `MINDER_API_BASE` env (default `http://minder:8080`).

- [ ] **Step 1: Implement** — in `minder/core/modules/remote.py`, at the top add a module constant and small helper (near the other constants):

```python
import os  # (if not already imported)

_MINDER_BASE = os.environ.get("MINDER_API_BASE", "http://minder:8080").rstrip("/")


def _push_blocks_best_effort(blocks: list) -> None:
    """Broadcast+persist any federated chat blocks a tool response carried.

    Lazy web import: keeps core import-light and never breaks the tool if the
    web layer is absent (e.g. CLI/tests).
    """
    if not blocks:
        return
    try:
        from minder.web import ui_bridge  # noqa: PLC0415 — lazy, best-effort
    except Exception:  # noqa: BLE001
        return
    for b in blocks:
        if not isinstance(b, dict):
            continue
        try:
            ui_bridge.push_remote_block(
                module=b.get("module", ""),
                remote_name=b["remote_name"], remote_entry=b["remote_entry"],
                component=b["component"], props=b.get("props"),
                block_id=b.get("block_id"), api_base=b.get("api_base"),
                height=b.get("height", "auto"), title=b.get("title"),
                session_id=None,  # contextvar → active agent-turn session
                persist=b.get("persist", True),
            )
        except Exception as exc:  # noqa: BLE001 — a bad block never breaks the tool
            ctx_logger = __import__("logging").getLogger(__name__)
            ctx_logger.warning("push_remote_block failed: %s", exc)
```

Then modify `_make_handler` (the closure returned for each proxy tool) so it (a) injects `_minder` context into the call arguments, and (b) pushes any `blocks` in the response. Locate the `def handler(**kwargs)` body; adjust:

```python
    def handler(**kwargs: Any) -> dict:
        query = str(kwargs.get("query") or kwargs.get("text") or "")
        # Hand the service the session + ingress so it can push proactively later.
        try:
            from minder.web import ui_bridge as _ub  # lazy
            _sid = _ub.current_session_id()
        except Exception:  # noqa: BLE001
            _sid = None
        call_args = dict(kwargs)
        call_args["_minder"] = {"session_id": _sid, "block_ingress": f"{_MINDER_BASE}/api/blocks/remote"}
        try:
            resp = conn.call_tool(tool_name, call_args)
        except ConnectorUnreachable:
            card = unavailable_card(query, conn.name)
            if ctx.broadcaster:
                try:
                    ctx.broadcaster({"type": "maintenance_answer", **card})
                except Exception as exc:  # noqa: BLE001
                    ctx.logger.warning("card broadcast failed: %s", exc)
            return {"success": True, "output": card, "_llm_suffix": UNAVAILABLE_SUFFIX}

        # Federated chat blocks the tool wants to mount (new):
        _push_blocks_best_effort(resp.get("blocks") or [])

        card = resp.get("card")
        if card and ctx.broadcaster:
            try:
                ctx.broadcaster({"type": "maintenance_answer", **card})
            except Exception as exc:  # noqa: BLE001
                ctx.logger.warning("card broadcast failed: %s", exc)
        out: dict = {"success": bool(resp.get("success", True)), "output": resp.get("output")}
        if resp.get("llm_suffix"):
            out["_llm_suffix"] = resp["llm_suffix"]
        return out
```

(Keep the rest of `_make_handler` and `build_remote_tool_specs` unchanged. If `os` is already imported at the top of `remote.py`, don't re-import.)

- [ ] **Step 2: Tests** — create `tests/test_proxy_tool_blocks.py`:

```python
"""Proxy handler injects _minder context and pushes federated blocks from a response."""
from __future__ import annotations

import sys
import types

from minder.core.modules import remote
from minder.core.skill_tools import SkillToolContext


class _Svc:
    connector_url = "http://mc:9200"
    health_path = "/connector/health"
    tools = [{"name": "maintenance_copilot_query", "description": "q",
              "parameters": {"type": "object"}}]


class _Manifest:
    service = _Svc()


class _Mod:
    name = "maintenance_copilot"
    manifest = _Manifest()


def test_handler_injects_minder_context_and_pushes_blocks(monkeypatch):
    # Fake ui_bridge so the lazy `from minder.web import ui_bridge` resolves in-test.
    pushed = []
    fake_ub = types.SimpleNamespace(
        current_session_id=lambda: "sess-42",
        push_remote_block=lambda **k: pushed.append(k) or "bid",
    )
    fake_web = types.ModuleType("minder.web")
    fake_web.ui_bridge = fake_ub
    monkeypatch.setitem(sys.modules, "minder.web", fake_web)
    monkeypatch.setitem(sys.modules, "minder.web.ui_bridge", fake_ub)

    captured = {}
    def fake_call(self, tool, arguments, timeout=110.0):
        captured.update(arguments)
        return {"success": True, "output": {"answer": "ok"},
                "blocks": [{"remote_name": "maintenance_copilot",
                            "remote_entry": "http://localhost:9200/dashboard/remoteEntry.js",
                            "component": "./AlertsBlock", "props": {"n": 2}}]}
    monkeypatch.setattr(remote.RemoteConnector, "call_tool", fake_call)

    specs = remote.build_remote_tool_specs(SkillToolContext(), [_Mod()])
    out = specs[0].handler(query="hi")
    assert out["success"] is True
    # _minder context handed to the service:
    assert captured["_minder"]["session_id"] == "sess-42"
    assert captured["_minder"]["block_ingress"].endswith("/api/blocks/remote")
    # the block was pushed:
    assert pushed and pushed[0]["component"] == "./AlertsBlock"
```

- [ ] **Step 3: Commit**

```bash
git add minder/core/modules/remote.py tests/test_proxy_tool_blocks.py
git commit -m "feat(modules): proxy tool pushes federated blocks + hands service session/ingress"
```

---

### Task 5: Keycloak realm — `minder-module` service client + `module-push` role

**Files:**
- Modify: `keycloak/realm-export.json`

**Interfaces:**
- Produces: a confidential client `minder-module` with service accounts enabled, whose service account holds the realm role `module-push`. A service-module obtains a token via client-credentials with this client's id/secret and calls the reverse ingress.

- [ ] **Step 1: Read the realm export** and note the shape (existing `clients: [...]`, `roles.realm: [...]`). Match it exactly.

- [ ] **Step 2: Add the realm role** — in `keycloak/realm-export.json`, under `roles.realm`, add:

```json
{ "name": "module-push", "description": "May push federated blocks into a chat session" }
```

- [ ] **Step 3: Add the confidential service client** — under `clients`, add (align field names with the existing `minder-backend` client in the same file; this is the canonical Keycloak client shape):

```json
{
  "clientId": "minder-module",
  "enabled": true,
  "publicClient": false,
  "serviceAccountsEnabled": true,
  "standardFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "secret": "CHANGE-ME-IN-ENV",
  "serviceAccountClientRoles": {},
  "attributes": {}
}
```

- [ ] **Step 4: Grant the role to the client's service account.** In `realm-export.json` this is done via the `"users"` array entry for the synthetic service-account user `service-account-minder-module` with `realmRoles: ["module-push"]`. Add that user entry (match the existing service-account user shape if `minder-backend` has one; otherwise add):

```json
{
  "username": "service-account-minder-module",
  "enabled": true,
  "serviceAccountClientId": "minder-module",
  "realmRoles": ["module-push"]
}
```

- [ ] **Step 5: Document the module-side env** — the service-module container needs (add to the `maintenance-copilot` service env in `docker-compose.yml`, and note in the integration guide): `KEYCLOAK_URL=http://keycloak:8080`, `KEYCLOAK_REALM=minder`, `MODULE_CLIENT_ID=minder-module`, `MODULE_CLIENT_SECRET=${MODULE_CLIENT_SECRET:-CHANGE-ME-IN-ENV}`, and `MINDER_API_BASE=http://minder:8080`. (Wiring the service's own token-fetch + push client is module code; out of scope for this plan's Minder-side changes — the plan delivers the Minder ingress + auth + descriptor; a follow-up adds the reference push client in `maintenance_copilot/backend`.)

- [ ] **Step 6: Validate JSON**

```bash
uv run --no-sync python -c "import json; json.load(open('keycloak/realm-export.json')); print('realm json ok')"
```

- [ ] **Step 7: Commit**

```bash
git add keycloak/realm-export.json docker-compose.yml
git commit -m "feat(keycloak): minder-module service client + module-push role for block push"
```

---

# Phase 2 — Frontend

### Task 6: Carry the remote descriptor through types + chat store

**Files:**
- Modify: `web-ui/src/types/index.ts`
- Modify: `web-ui/src/stores/chat.ts`

**Interfaces:**
- Produces: chat messages of `role:'custom_block'` may carry `render:'remote'` + `remote_name`, `remote_entry`, `component`, `api_base`, `props`, `block_props` (existing). WS `custom_block` handler and the persisted-message loader both populate them; `custom_block_update`/`custom_block_remove` are reused unchanged (they key on `block_id`).

- [ ] **Step 1: Extend the chat-message type** in `web-ui/src/types/index.ts` — find the message interface that has `block_id`/`block_src` and add:

```typescript
  render?: 'iframe' | 'remote';
  remote_name?: string | null;
  remote_entry?: string | null;
  component?: string | null;
  api_base?: string | null;
```

- [ ] **Step 2: WS `custom_block` handler** in `web-ui/src/stores/chat.ts` (~line 786, `wsClient.on('custom_block', ...)`) — when `message.data.render === 'remote'`, store the descriptor fields instead of `block_src`. Adjust the pushed message object:

```typescript
        const d = message.data;
        // ... existing id/role/timestamp fields ...
        render: d.render === 'remote' ? 'remote' : 'iframe',
        block_id: d.block_id,
        block_src: d.src ?? null,            // iframe path (undefined for remote)
        block_props: d.props ?? {},
        remote_name: d.remote_name ?? null,
        remote_entry: d.remote_entry ?? null,
        component: d.component ?? null,
        api_base: d.api_base ?? null,
        block_title: d.title ?? null,
```
(Keep every existing field the handler already set; only ADD the five remote fields + `render`.)

- [ ] **Step 3: Persisted-message loader** (~line 99, `if (msg.role === 'custom_block')`) — mirror the same mapping from `meta` (the persisted payload) so a reloaded remote block rehydrates:

```typescript
        const meta = msg.metadata ?? {};
        return {
          // ... existing fields ...
          render: meta.render === 'remote' ? 'remote' : 'iframe',
          block_id: meta.block_id,
          block_src: meta.src ?? null,
          block_props: meta.props ?? {},
          remote_name: meta.remote_name ?? null,
          remote_entry: meta.remote_entry ?? null,
          component: meta.component ?? null,
          api_base: meta.api_base ?? null,
          block_title: meta.title ?? null,
        };
```

(`custom_block_update` at ~812 already updates `block_props` by `block_id` — remote blocks reuse it verbatim, so live updates work. `custom_block_remove` at ~836 is likewise reused. No change needed there. Use the real field name the store uses for block props — grep `block_props` vs `props` in chat.ts and match it.)

- [ ] **Step 4: Commit**

```bash
git add web-ui/src/types/index.ts web-ui/src/stores/chat.ts
git commit -m "feat(web-ui): carry federated block descriptor through chat store + rehydrate"
```

---

### Task 7: `RemoteBlock` renderer + `MessageList` branch (bidirectional)

**Files:**
- Create: `web-ui/src/components/Chat/RemoteBlock.tsx`
- Create: `web-ui/src/components/Chat/RemoteBlock.test.tsx`
- Modify: `web-ui/src/components/Chat/MessageList.tsx`

**Interfaces:**
- Consumes: `registerRemote`, `loadRemoteComponent` (`web-ui/src/lib/federation.ts`); the chat message's remote fields (Task 6); the chat store's send-user-message action.
- Produces: `RemoteBlock` — loads the module's federated `component` and renders it in-host with `{ props, apiBase, sendMessage, blockId }`. `MessageList` renders `RemoteBlock` when `message.render === 'remote'`, else the existing `SandboxedBlock` iframe.

- [ ] **Step 1: Implement `RemoteBlock`** — create `web-ui/src/components/Chat/RemoteBlock.tsx`:

```tsx
import { useEffect, useState, type ComponentType } from 'react';
import { registerRemote, loadRemoteComponent } from '../../lib/federation';
import { useChatStore } from '../../stores/chat';

interface RemoteBlockProps {
  blockId: string;
  remoteName: string;
  remoteEntry: string;
  component: string;
  apiBase: string;
  props: Record<string, any>;
}

/**
 * Renders a service-module's federated React component natively in the chat
 * (no iframe), sharing the host's React. The component receives its data plus
 * `apiBase` (call its own connector) and `sendMessage` (act through the agent).
 */
export function RemoteBlock(p: RemoteBlockProps) {
  const [Comp, setComp] = useState<ComponentType<any> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sendUserMessage = useChatStore((s) => s.sendMessage);

  useEffect(() => {
    let alive = true;
    if (!p.remoteName || !p.remoteEntry || !p.component) {
      setError('block is missing federation fields');
      return;
    }
    registerRemote({ name: p.remoteName, entry: p.remoteEntry });
    loadRemoteComponent(p.remoteName, p.component)
      .then((c) => { if (alive) setComp(() => c); })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [p.remoteName, p.remoteEntry, p.component]);

  if (error) return <div className="p-3 text-sm text-red-400">Block failed: {error}</div>;
  if (!Comp) return <div className="p-3 text-sm text-text-300">Loading block…</div>;
  return (
    <Comp
      {...p.props}
      apiBase={p.apiBase}
      blockId={p.blockId}
      sendMessage={(text: string) => sendUserMessage(text)}
    />
  );
}
```

(Confirm the chat store's send action name via grep — it may be `sendMessage`, `send`, or `submitMessage`. Use the real one; the `sendMessage` prop handed to the block should inject a user message exactly as the input box does. If the store's action needs more than text, wrap it so the block only passes text.)

- [ ] **Step 2: Branch in `MessageList.tsx`** — at line ~235, where it currently does `if (message.role === 'custom_block' && message.block_id && message.block_src)`, add a remote branch BEFORE the iframe branch:

```tsx
  if (message.role === 'custom_block' && message.render === 'remote' && message.block_id) {
    return (
      <RemoteBlock
        key={message.block_id}
        blockId={message.block_id}
        remoteName={message.remote_name ?? ''}
        remoteEntry={message.remote_entry ?? ''}
        component={message.component ?? ''}
        apiBase={message.api_base ?? ''}
        props={message.block_props ?? {}}
      />
    );
  }
  // existing iframe branch stays below, unchanged:
  if (message.role === 'custom_block' && message.block_id && message.block_src) { /* SandboxedBlock */ }
```

Add the import: `import { RemoteBlock } from './RemoteBlock';`.

- [ ] **Step 3: Test** — create `web-ui/src/components/Chat/RemoteBlock.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../lib/federation', () => ({
  registerRemote: vi.fn(),
  loadRemoteComponent: vi.fn(async () =>
    (props: any) => <div>block-ok:{props.apiBase}:{props.count}</div>),
}));
vi.mock('../../stores/chat', () => ({
  useChatStore: (sel: any) => sel({ sendMessage: vi.fn() }),
}));

import { RemoteBlock } from './RemoteBlock';

describe('RemoteBlock', () => {
  it('registers the remote and renders the component with apiBase + props', async () => {
    const fed = await import('../../lib/federation');
    render(<RemoteBlock blockId="b1" remoteName="maintenance_copilot"
      remoteEntry="http://localhost:9200/dashboard/remoteEntry.js"
      component="./AlertsBlock" apiBase="http://localhost:9200" props={{ count: 5 }} />);
    await waitFor(() =>
      expect(screen.getByText(/block-ok:http:\/\/localhost:9200:5/)).toBeTruthy());
    expect(fed.registerRemote).toHaveBeenCalledWith({
      name: 'maintenance_copilot',
      entry: 'http://localhost:9200/dashboard/remoteEntry.js',
    });
  });
});
```

- [ ] **Step 4: Commit**

```bash
git add web-ui/src/components/Chat/RemoteBlock.tsx web-ui/src/components/Chat/RemoteBlock.test.tsx web-ui/src/components/Chat/MessageList.tsx
git commit -m "feat(web-ui): render federated chat blocks natively in-host (RemoteBlock)"
```

---

# Phase V — Consolidated test + verify  *(run once, at the end)*

- [ ] **V1: Python unit tests**

```bash
uv run --no-sync pytest tests/test_push_remote_block.py tests/test_service_auth.py \
  tests/test_blocks_remote_route.py tests/test_proxy_tool_blocks.py -v
uv run --no-sync pytest tests/ -q      # full suite — no regressions
```
Expected: all green. Fix any failure at its source (don't weaken assertions).

- [ ] **V2: Frontend build + component test**

```bash
cd web-ui && npx vitest run src/components/Chat/RemoteBlock.test.tsx && npm run build
```
Expected: test passes; `tsc + vite build` succeeds (new type fields + RemoteBlock type-check).

- [ ] **V3: Realm JSON**

```bash
uv run --no-sync python -c "import json; json.load(open('keycloak/realm-export.json')); print('realm ok')"
```

- [ ] **V4: Real e2e (agent-driven feeder — no browser needed)** — with the stack up and a real `OPENAI_API_KEY`, have the `maintenance_copilot` connector return a `blocks:[…]` descriptor from a tool call; confirm a `custom_block` WS event with `render:"remote"` is broadcast and a `custom_block` message is persisted (check the session store). This exercises Feeder 1 end-to-end without a browser.

- [ ] **V5: Deferred to user (browser + Keycloak service token)** — record the exact commands in a short note:
  - obtain a token: `curl -s -X POST "$KEYCLOAK_URL/realms/minder/protocol/openid-connect/token" -d grant_type=client_credentials -d client_id=minder-module -d client_secret=$MODULE_CLIENT_SECRET | jq -r .access_token`
  - proactive push: `curl -X POST localhost:8080/api/blocks/remote/push -H "Authorization: Bearer $TOK" -H 'content-type: application/json' -d '{"session_id":"<sid>","module":"maintenance_copilot","remote_name":"maintenance_copilot","remote_entry":"http://localhost:9200/dashboard/remoteEntry.js","component":"./AlertsBlock","props":{"n":1}}'`
  - open the chat: confirm the block renders natively (React DevTools shows the remote component in the host tree, no iframe), a follow-up `/update` changes it live, and the block's `sendMessage` reaches the agent; reload rehydrates the block.

- [ ] **V6: Final commit**

```bash
git add -A && git commit -m "test(federated-blocks): consolidated verification (phase V)"
```

---

## Self-Review Notes (author)

- **Spec coverage:** descriptor §1 → Task 1 (+ Task 6 FE mirror); WS/persistence §2 → Task 1 + Task 6; Feeder 1 §3 → Task 4; Feeder 2 + Keycloak §4 → Tasks 2/3/5; FE render §5 → Task 7; bidirectionality §6 → Task 7 (`apiBase`/`sendMessage`/`blockId` props) + reuse of `custom_block_update`; persistence/rehydration §7 → Task 6 loader; security §8 → Task 2 (`require_service_principal`) + first-party-trust note; phasing §Build → task order; testing §Testing → Phase V.
- **Deferred (matches spec):** the reference module's own token-fetch + push *client code* (in `maintenance_copilot/backend`) is a follow-up — this plan delivers the Minder-side ingress, auth, descriptor, and render path. The grounded/browser e2e is V5 (user-run).
- **Type consistency:** descriptor keys identical across `push_remote_block`, the ingress body, the proxy `blocks:` handler, the WS `data`, persistence `meta`, and the FE message fields (`render/remote_name/remote_entry/component/api_base/props`). `MODULE_PUSH_ROLE="module-push"` used in Task 2 and Task 5. `custom_block_update`/`_remove` reused unchanged for remote blocks.
- **Grep-and-match flags (unknowns that depend on real code):** the chat-store message field for block props (`block_props` vs `props`) — Task 6/7 say to match the real name; the chat store's send-message action name — Task 7 says to grep and use the real one; the async test marker (`pytest-asyncio` vs `anyio`) — Task 2 says to match the repo convention; the `server.py` router-registration style — Task 3 says to match the existing `blocks` router.
