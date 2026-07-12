# SDK Integration Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Execution mode is code-all-then-verify (user preference): implement every task in order WITHOUT running tests per-task; write each task's tests alongside its code, then run the whole suite + verification once in the final Phase V.**

**Goal:** Extend `minder_module_sdk` (+ minimal Minder host support) with 10 integration enhancements: block/invoke ergonomics, readiness gating, typed params, declarative auth, identity/session forwarding, an `MinderClient` reverse-push channel (blocks + artifacts), streaming block events, and manifest enrichment.

**Architecture:** Additive. The SDK gains `Connector` methods + an `MinderClient` (httpx-only, never imports `minder`). The host gains two `SkillToolContext` fields (wired like `push_block`), an identity-forwarding tweak in the tool proxy, a `_run_stream` `block` branch, a reconciler readiness check, and one new service-principal route for artifact push. Reuse the existing reverse-push ingress and federated-block machinery.

**Tech Stack:** Python 3.12 + FastAPI + pydantic v2 + httpx (SDK); pytest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-10-sdk-integration-enhancements-design.md`.
- **SDK never imports `minder`.** `MinderClient` uses only `httpx` + env config.
- **MCP is out of scope** (separate interop track).
- **Roles:** reverse-push + artifact push require Keycloak realm role `module-push`; register/deregister use `module-register`. The `minder-module` service client holds BOTH.
- **`params_model` is opt-in** and mutually exclusive with hand-written `parameters=`.
- **Identity forwarding is first-party trust:** only `{username, email}` + `session_id`, no token.
- **`MinderClient` raises `MinderClientError`** on push failures (proactive action — caller decides), unlike announce which swallows.
- **Fail-closed preserved:** `requires_auth` reject / `params_model` invalid / handler exception → structured `{success: False, ...}`, never a 500.
- **Test command:** `uv run --no-sync pytest <path>` (never bare `pytest`).
- **Commits:** no `Co-Authored-By: Claude` trailer.
- **`docs/` is gitignored — stage plan/spec with `git add -f`. `tests/` is gitignored — stage new test files with `git add -f`.**
- **EXECUTION: code all tasks, then Phase V runs all tests + verify once.**

---

## File Structure

**SDK — created:**
- `minder_module_sdk/minder_module_sdk/client.py` — `MinderClient`, `MinderClientError`.
- `minder_module_sdk/tests/test_connector_ext.py` — `conn.block`/`invoke`/`readiness`/`params_model`/`requires_auth`/manifest.
- `minder_module_sdk/tests/test_client.py` — `MinderClient` (httpx MockTransport).

**SDK — modified:**
- `minder_module_sdk/minder_module_sdk/connector.py` — the `Connector` additions.
- `minder_module_sdk/minder_module_sdk/__init__.py` — export `MinderClient`, `MinderClientError`.

**Host — created:**
- `minder/web/routes/artifacts_remote.py` — service-principal artifact push ingress.
- `tests/test_ctx_identity_forwarding.py`, `tests/test_stream_block_event.py`, `tests/test_readiness_gating.py`, `tests/test_artifacts_remote_route.py`.

**Host — modified:**
- `minder/core/skill_tools.py` — `SkillToolContext.session_id`, `.principal`.
- `minder/web/ws_tool_broadcaster.py` — wire the two fields.
- `minder/core/modules/remote.py` — `_make_handler` forwards identity; `_run_stream` `block` event.
- `minder/core/modules/watcher.py` — reconciler respects `health.ready`.
- `minder/core/modules/registry.py` — connector record carries a `ready` flag; `mark_connector_ready` gates on it.
- `minder/web/server.py` — register `artifacts_remote_router`.
- `minder/web/routes/__init__.py` — export `artifacts_remote_router`.
- `keycloak/realm-export.json` — grant `module-push` to `service-account-minder-module`.

---

# Phase A — SDK ergonomics & DX

### Task A1: `conn.block()` method

**Files:**
- Modify: `minder_module_sdk/minder_module_sdk/connector.py`
- Test: `minder_module_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Consumes: the existing free `block(component, props, *, remote_name, remote_entry, height, title)` from `.cards`.
- Produces: `Connector.block(self, component: str, props: Optional[dict] = None, *, height="auto", title=None) -> dict`.

- [ ] **Step 1: Implement.** Add to `Connector` (import `block as _block_descriptor` from `.cards` at the top of `connector.py`, aliased to avoid clashing with any local name):

```python
    def block(self, component: str, props: Optional[dict] = None, *,
              height: Any = "auto", title: Optional[str] = None) -> dict:
        """Build a federated chat-block descriptor for THIS module — fills
        remote_name (self.name) and remote_entry ($MINDER_MODULE_REMOTE_ENTRY)."""
        from .cards import block as _b
        remote_entry = os.environ.get("MINDER_MODULE_REMOTE_ENTRY", "")
        return _b(component, props, remote_name=self.name,
                  remote_entry=remote_entry, height=height, title=title)
```

- [ ] **Step 2: Test** (in `minder_module_sdk/tests/test_connector_ext.py`):

```python
import os
from minder_module_sdk import Connector


def test_conn_block_fills_name_and_remote_entry(monkeypatch):
    monkeypatch.setenv("MINDER_MODULE_REMOTE_ENTRY", "http://h:9300/dashboard/remoteEntry.js")
    conn = Connector("my_module")
    d = conn.block("./MyAnswer", {"answer": "hi"})
    assert d["render"] == "remote"
    assert d["remote_name"] == "my_module"
    assert d["component"] == "./MyAnswer"
    assert d["remote_entry"] == "http://h:9300/dashboard/remoteEntry.js"
    assert d["api_base"] == "http://h:9300"
    assert d["props"] == {"answer": "hi"}
```

### Task A2: `conn.invoke()` public test helper

**Files:**
- Modify: `minder_module_sdk/minder_module_sdk/connector.py`
- Test: `minder_module_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Consumes: `Connector._call`, `Principal`.
- Produces: `Connector.invoke(self, tool_name: str, arguments: dict, principal: Optional[Principal] = None, session_id: Optional[str] = None) -> dict`. Raises `KeyError` for an unknown tool. Returns the normalized envelope.

- [ ] **Step 1: Implement.** Add to `Connector`:

```python
    def invoke(self, tool_name: str, arguments: dict, *,
               principal: Optional[Principal] = None,
               session_id: Optional[str] = None) -> dict:
        """Invoke a registered tool in-process (for unit tests) — bypasses HTTP.
        Returns the same envelope the /connector/tools/{name} endpoint returns."""
        tool = self._tools[tool_name]
        return self._call(tool, arguments, principal or Principal(), session_id=session_id)
```

*(Note: `_call` gains a `session_id` param in Task B4 — until then omit it. The plan's
Task B4 updates `_call`'s signature; write `invoke` with `session_id` from the start and
implement B4 so it accepts it.)*

- [ ] **Step 2: Test:**

```python
def test_conn_invoke_runs_tool_in_process():
    conn = Connector("m")

    @conn.tool("echo", parameters={"type": "object", "properties": {"q": {"type": "string"}}})
    def echo(q: str = ""):
        return {"output": q.upper()}

    out = conn.invoke("echo", {"q": "hi"})
    assert out["success"] is True and out["output"] == "HI"
```

### Task A3: `@conn.readiness_probe` + health `ready`

**Files:**
- Modify: `minder_module_sdk/minder_module_sdk/connector.py`
- Test: `minder_module_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Produces: `Connector.readiness_probe(fn)` decorator registering a `() -> bool | dict`. `/connector/health` response gains `"ready": bool` (True when no probe; a probe returning `{"ready": ...}` or a bool; a raising probe → False).

- [ ] **Step 1: Implement.** In `__init__` add `self._readiness_probes: list[Callable[[], Any]] = []`. Add the decorator + a `_ready()` helper, and include `ready` in the health route:

```python
    def readiness_probe(self, fn: Callable[[], Any]) -> Callable[[], Any]:
        """Register a readiness check: () -> bool | {"ready": bool, ...}. While any
        probe reports not-ready, Minder keeps this module's tools OUT of the agent
        catalog (the connector is alive but not serving yet)."""
        self._readiness_probes.append(fn)
        return fn

    def _ready(self) -> bool:
        for probe in self._readiness_probes:
            try:
                res = probe()
                ok = res.get("ready", True) if isinstance(res, dict) else bool(res)
                if not ok:
                    return False
            except Exception as exc:  # noqa: BLE001 — a failing probe means not-ready
                logger.warning("readiness probe failed: %s", exc)
                return False
        return True
```

In the `health()` route add `"ready": self._ready()` to the returned dict.

- [ ] **Step 2: Test** (drive via a `TestClient`):

```python
from fastapi.testclient import TestClient


def test_health_ready_defaults_true():
    conn = Connector("m")
    c = TestClient(conn.asgi())
    assert c.get("/connector/health").json()["ready"] is True


def test_readiness_probe_can_report_not_ready():
    conn = Connector("m")

    @conn.readiness_probe
    def probe():
        return {"ready": False, "detail": "ingesting"}

    c = TestClient(conn.asgi())
    assert c.get("/connector/health").json()["ready"] is False
```

### Task A4: `params_model` — typed parameters

**Files:**
- Modify: `minder_module_sdk/minder_module_sdk/connector.py`
- Test: `minder_module_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Consumes: pydantic v2 (already an SDK dep).
- Produces: `@conn.tool(..., params_model=<BaseModel subclass>)`. When given, `parameters` is derived from `params_model.model_json_schema()` and incoming `arguments` are validated before the handler runs; a `ValidationError` yields `{success: False, output: "invalid arguments: …", card: None, card_type: None, llm_suffix: None, blocks: None}`. `params_model` and `parameters=` are mutually exclusive (raise `ValueError` at registration if both given).

- [ ] **Step 1: Extend `_Tool`** — add `params_model: Optional[type] = None` field.

- [ ] **Step 2: Update the `tool` decorator signature + body:**

```python
    def tool(self, name: str, *, description: str = "", parameters: Optional[dict] = None,
             card_type: Optional[str] = None, streaming: bool = False,
             requires_auth: bool = False, params_model: Optional[type] = None
             ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if params_model is not None and parameters is not None:
            raise ValueError("pass either params_model or parameters, not both")
        params = (params_model.model_json_schema() if params_model is not None
                  else (parameters or {"type": "object", "properties": {}}))

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._tools[name] = _Tool(name, description, params, fn, card_type,
                                      streaming, requires_auth=requires_auth,
                                      params_model=params_model)
            return fn

        return deco
```

*(Update the `_Tool` dataclass to add `requires_auth: bool = False` and `params_model: Optional[type] = None` fields — see Task A5 for `requires_auth`.)*

- [ ] **Step 3: Validate in `_call`** — at the top of `_call`, after resolving `tool`, before calling the handler:

```python
        if tool.params_model is not None:
            try:
                validated = tool.params_model(**arguments)
                arguments = validated.model_dump()
            except Exception as exc:  # noqa: BLE001 — pydantic ValidationError etc.
                return {"success": False, "output": f"invalid arguments: {exc}",
                        "card": None, "card_type": None, "llm_suffix": None, "blocks": None}
```

- [ ] **Step 4: Test:**

```python
from pydantic import BaseModel


def test_params_model_derives_schema_and_validates():
    conn = Connector("m")

    class P(BaseModel):
        q: str
        k: int = 5

    @conn.tool("search", params_model=P)
    def search(q: str, k: int = 5):
        return {"output": f"{q}:{k}"}

    # Schema derived:
    assert conn._tools["search"].parameters["properties"]["q"]["type"] == "string"
    # Valid:
    assert conn.invoke("search", {"q": "hi", "k": 3})["output"] == "hi:3"
    # Invalid (missing required q):
    bad = conn.invoke("search", {"k": 3})
    assert bad["success"] is False and "invalid arguments" in bad["output"]


def test_params_model_and_parameters_are_mutually_exclusive():
    conn = Connector("m")
    import pytest
    with pytest.raises(ValueError):
        @conn.tool("x", parameters={"type": "object"}, params_model=BaseModel)
        def x():
            return {}
```

### Task A5: `requires_auth`

**Files:**
- Modify: `minder_module_sdk/minder_module_sdk/connector.py`
- Test: `minder_module_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Consumes: `Principal.is_authenticated`, the `_Tool.requires_auth` field (added in A4).
- Produces: `@conn.tool(..., requires_auth=True)`. When the effective principal is not authenticated, `_call` returns `{success: False, output: "authentication required", card: None, card_type: None, llm_suffix: None, blocks: None}` without running the handler.

- [ ] **Step 1: Gate in `_call`** — after the `params_model` validation block, before invoking the handler:

```python
        if tool.requires_auth and not principal.is_authenticated:
            return {"success": False, "output": "authentication required",
                    "card": None, "card_type": None, "llm_suffix": None, "blocks": None}
```

- [ ] **Step 2: Test:**

```python
from minder_module_sdk import Connector
from minder_module_sdk.connector import Principal


def test_requires_auth_blocks_anonymous():
    conn = Connector("m")

    @conn.tool("secret", requires_auth=True)
    def secret(principal=None):
        return {"output": "ok"}

    anon = conn.invoke("secret", {})
    assert anon["success"] is False and anon["output"] == "authentication required"
    authed = conn.invoke("secret", {}, principal=Principal(username="alice", email="a@x"))
    assert authed["output"] == "ok"
```

---

# Phase B — Identity & session on the agent-tool path

### Task B1: `SkillToolContext` fields

**Files:**
- Modify: `minder/core/skill_tools.py`

**Interfaces:**
- Produces: `SkillToolContext.session_id: str | None = None` and `SkillToolContext.principal: dict | None = None` (mutable, like `broadcaster`).

- [ ] **Step 1: Add the fields** after `broadcaster` in the `SkillToolContext` dataclass:

```python
    # The active agent turn's session id + acting user, wired by the web session
    # layer (like broadcaster/push_block). Forwarded to service-module connectors
    # so a tool can gate on identity and reverse-push into the right session.
    session_id: str | None = None
    principal: dict[str, Any] | None = None
```

### Task B2: wire them in the broadcaster

**Files:**
- Modify: `minder/web/ws_tool_broadcaster.py`

**Interfaces:**
- Consumes: `WebSocketToolBroadcaster.session_id` (already an attribute); `SkillToolContext.session_id`/`.principal`.

- [ ] **Step 1: Set them** where `skill_ctx.broadcaster`/`skill_ctx.push_block` are assigned in `__init__`:

```python
        if skill_ctx is not None:
            skill_ctx.broadcaster = self._broadcast_skill_event
            skill_ctx.push_block = self._push_remote_block
            skill_ctx.session_id = self.session_id
```

*(Principal: if the broadcaster has the acting user available, also set `skill_ctx.principal = {"username": ..., "email": ...}`. If it does not carry a user, leave `skill_ctx.principal = None` — the forwarding in B3 handles `None` by sending no principal. Read the surrounding `__init__` to see whether a user/principal is in scope; wire it if present, else leave None and note it.)*

### Task B3: `_make_handler` forwards identity

**Files:**
- Modify: `minder/core/modules/remote.py`

**Interfaces:**
- Consumes: `ctx.session_id`, `ctx.principal`; `RemoteConnector.call_tool(tool, arguments, principal=…)` (already supports `principal`); `_auth_headers`.

- [ ] **Step 1: Add a session header helper.** In `_auth_headers(name, principal)`, add an optional `session_id`:

```python
def _auth_headers(name: str, principal: Optional[dict], session_id: Optional[str] = None) -> dict:
    headers: dict = {}
    token = _module_token(name)
    if token:
        headers["X-Minder-Module-Token"] = token
    if principal:
        headers["X-Minder-Principal"] = json.dumps(principal, separators=(",", ":"))
    if session_id:
        headers["X-Minder-Session"] = session_id
    return headers
```

- [ ] **Step 2: Thread `session_id` through `call_tool`.** Update `RemoteConnector.call_tool` signature to `call_tool(self, tool, arguments, timeout=110.0, principal=None, session_id=None)` and pass `session_id` into `_auth_headers(self.name, principal, session_id)`.

- [ ] **Step 3: Forward from the handler.** In `_make_handler`'s non-stream path, replace `resp = conn.call_tool(tool_name, kwargs)` with:

```python
            resp = conn.call_tool(tool_name, kwargs,
                                  principal=ctx.principal, session_id=ctx.session_id)
```

And in `_run_stream`/`stream_tool` (Task C2 area) pass `session_id`/`principal` into the stream client the same way (the stream client's `_auth_headers` call gains `ctx.session_id`).

### Task B4: SDK reads `X-Minder-Session`, injects `session_id`

**Files:**
- Modify: `minder_module_sdk/minder_module_sdk/connector.py`
- Test: `minder_module_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Produces: `_call(self, tool, arguments, principal, *, session_id: Optional[str] = None)`. A handler declaring `session_id` (or `**kwargs`) receives it, like `principal`. `_principal_from_headers` unchanged; add `_session_from_headers(request) -> Optional[str]` reading `X-Minder-Session`. The `call_tool` and `stream_tool` endpoints pass the parsed session into `_call`/`_sse`.

- [ ] **Step 1: Parse the header.** Add:

```python
def _session_from_headers(request: Request) -> Optional[str]:
    return request.headers.get("X-Minder-Session") or None
```

- [ ] **Step 2: Inject into the handler.** Update `_call` to accept `session_id` and inject it when the handler accepts it:

```python
    def _call(self, tool: _Tool, arguments: dict, principal: Principal, *,
              session_id: Optional[str] = None) -> dict:
        # ... params_model validation (A4) and requires_auth (A5) first ...
        kwargs = dict(arguments)
        if _accepts_principal(tool.handler):
            kwargs["principal"] = principal
        if session_id is not None and (_accepts_arg(tool.handler, "session_id")
                                       or _has_var_keyword(tool.handler)):
            kwargs["session_id"] = session_id
        # ... existing try/except body ...
```

- [ ] **Step 3: Pass it in from the endpoints.** In the `call_tool` route: `session_id = _session_from_headers(request)` then `return self._call(tool, body.get("arguments") or {}, principal, session_id=session_id)`. Do the same in `stream_tool` → `_sse(tool, args, principal, session_id=session_id)` (thread `session_id` through `_sse` and its inner `_call`/handler invocation).

- [ ] **Step 4: Test:**

```python
def test_session_id_injected_into_handler():
    conn = Connector("m")
    seen = {}

    @conn.tool("cap")
    def cap(session_id=None, **kwargs):
        seen["sid"] = session_id
        return {"output": "ok"}

    conn.invoke("cap", {}, session_id="sess-123")
    assert seen["sid"] == "sess-123"
```

---

# Phase C — Bidirectional outbound

### Task C1: `MinderClient` reverse-push

**Files:**
- Create: `minder_module_sdk/minder_module_sdk/client.py`
- Modify: `minder_module_sdk/minder_module_sdk/connector.py` (add `conn.minder_client()`), `minder_module_sdk/minder_module_sdk/__init__.py`
- Test: `minder_module_sdk/tests/test_client.py`

**Interfaces:**
- Consumes: `resolve_announce_config`, `_auth_headers` (from `announce.py`); the host ingress `/api/blocks/remote/{push,update,remove}` whose bodies are: push `{session_id, module, remote_name, remote_entry, component, props?, block_id?, api_base?, height, title, persist}`; update `{session_id, block_id, props}`; remove `{session_id, block_id}`.
- Produces:
  - `class MinderClientError(RuntimeError)`.
  - `class MinderClient` with `__init__(self, module, cfg)`, methods `push_block(session_id, component, props=None, *, remote_entry=None, height="auto", title=None, block_id=None) -> str`, `update_block(session_id, block_id, props) -> None`, `remove_block(session_id, block_id) -> None`. `remote_entry` defaults to `cfg.remote_entry`; `remote_name` = `module`; `api_base` derived from `remote_entry`.
  - `Connector.minder_client() -> MinderClient` — builds one from `resolve_announce_config()`; raises `MinderClientError` if announce config is absent.

- [ ] **Step 1: Implement `client.py`:**

```python
"""MinderClient — a module's proactive channel back into Minder (reverse-push).

Never imports ``minder``; httpx + env only. Use it to push/update/remove a
federated chat block into a live session outside a tool call (e.g. an async job
reporting progress). Requires the Keycloak realm role ``module-push``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .announce import AnnounceConfig, _auth_headers

logger = logging.getLogger("minder_module_sdk.client")


class MinderClientError(RuntimeError):
    """A reverse-push call to Minder failed."""


class MinderClient:
    def __init__(self, module: str, cfg: AnnounceConfig) -> None:
        self.module = module
        self.cfg = cfg

    def _post(self, path: str, payload: dict) -> httpx.Response:
        url = f"{self.cfg.minder_url}{path}"
        try:
            resp = httpx.post(url, json=payload, headers=_auth_headers(self.cfg), timeout=15)
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as exc:
            logger.warning("minder client %s failed: %s", path, exc)
            raise MinderClientError(str(exc)) from exc

    def push_block(self, session_id: str, component: str, props: Optional[dict] = None, *,
                   remote_entry: Optional[str] = None, height: Any = "auto",
                   title: Optional[str] = None, block_id: Optional[str] = None) -> str:
        entry = remote_entry or self.cfg.remote_entry or ""
        api_base = entry.split("/dashboard/")[0] if "/dashboard/" in entry else None
        payload = {"session_id": session_id, "module": self.module,
                   "remote_name": self.module, "remote_entry": entry,
                   "component": component, "props": props or {}, "block_id": block_id,
                   "api_base": api_base, "height": height, "title": title, "persist": True}
        return self._post("/api/blocks/remote/push", payload).json()["block_id"]

    def update_block(self, session_id: str, block_id: str, props: dict) -> None:
        self._post("/api/blocks/remote/update",
                   {"session_id": session_id, "block_id": block_id, "props": props})

    def remove_block(self, session_id: str, block_id: str) -> None:
        self._post("/api/blocks/remote/remove",
                   {"session_id": session_id, "block_id": block_id})
```

- [ ] **Step 2: `conn.minder_client()`** in `connector.py`:

```python
    def minder_client(self) -> "MinderClient":
        """Build a reverse-push client for this module (needs MINDER_URL + a
        module-push service token). Raises MinderClientError if unconfigured."""
        from .announce import resolve_announce_config
        from .client import MinderClient, MinderClientError
        cfg = resolve_announce_config()
        if cfg is None:
            raise MinderClientError("announce config absent (MINDER_URL/CONNECTOR_URL unset)")
        return MinderClient(self.name, cfg)
```

- [ ] **Step 3: Export** in `__init__.py`: `from .client import MinderClient, MinderClientError` and add both to `__all__`.

- [ ] **Step 4: Test** (`minder_module_sdk/tests/test_client.py`, httpx MockTransport):

```python
import httpx
from minder_module_sdk.announce import AnnounceConfig
from minder_module_sdk.client import MinderClient, MinderClientError


def _client(handler):
    cfg = AnnounceConfig(minder_url="http://minder:8000", connector_url="http://m:9300",
                         remote_entry="http://m:9300/dashboard/remoteEntry.js")
    c = MinderClient("m", cfg)
    # inject a mock transport by monkeypatching httpx.post used inside _post
    return c, cfg


def test_push_block_posts_expected_payload(monkeypatch):
    captured = {}
    def fake_post(url, json, headers, timeout):
        captured["url"] = url; captured["json"] = json
        return httpx.Response(200, json={"block_id": "b1"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("minder_module_sdk.client.httpx.post", fake_post)
    c, _ = _client(None)
    bid = c.push_block("sess", "./Job", {"pct": 0})
    assert bid == "b1"
    assert captured["url"] == "http://minder:8000/api/blocks/remote/push"
    assert captured["json"]["remote_name"] == "m"
    assert captured["json"]["api_base"] == "http://m:9300"


def test_push_error_raises(monkeypatch):
    def fake_post(url, json, headers, timeout):
        return httpx.Response(500, request=httpx.Request("POST", url))
    monkeypatch.setattr("minder_module_sdk.client.httpx.post", fake_post)
    c, _ = _client(None)
    import pytest
    with pytest.raises(MinderClientError):
        c.update_block("sess", "b1", {"pct": 9})
```

### Task C2: `block` event in streaming

**Files:**
- Modify: `minder/core/modules/remote.py` (`_run_stream`)
- Test: `tests/test_stream_block_event.py`

**Interfaces:**
- Consumes: `ctx.push_block` (already wired), the stream event loop in `_run_stream`.
- Produces: a `block` event branch — `{"event": "block", "block": {…descriptor…}}` → `ctx.push_block(block, conn.name)` when `ctx.push_block` and `block.get("remote_entry")`.

- [ ] **Step 1: Add the branch** in `_run_stream`'s per-event `if/elif`:

```python
            elif etype == "block":
                blk = evt.get("block") or {}
                if ctx.push_block and blk.get("remote_entry"):
                    try:
                        ctx.push_block(blk, conn.name)
                    except Exception as exc:  # noqa: BLE001 — a block push must never break the stream
                        ctx.logger.warning("stream block push failed for %s: %s", conn.name, exc)
```

- [ ] **Step 2: Test** (`tests/test_stream_block_event.py`) — stub a connector whose `stream_tool` yields a `block` event, assert `ctx.push_block` is called:

```python
from minder.core.modules import remote
from minder.core.skill_tools import SkillToolContext


class _StreamConn:
    name = "m"
    def stream_tool(self, tool, arguments, timeout=300.0):
        yield {"event": "block", "block": {"remote_entry": "http://h/dashboard/x", "component": "./J"}}
        yield {"event": "final", "success": True, "output": "done"}
    def call_tool(self, *a, **k):
        return {"success": True, "output": "done"}


def test_stream_block_event_pushes_block():
    ctx = SkillToolContext()
    pushed = []
    ctx.push_block = lambda blk, module: pushed.append((blk, module))
    result = remote._run_stream(ctx, _StreamConn(), "t", {}, "q")
    assert pushed and pushed[0][1] == "m"
    assert result["output"] == "done"
```

### Task C3: artifact push ingress

**Files:**
- Create: `minder/web/routes/artifacts_remote.py`
- Modify: `minder/web/routes/__init__.py`, `minder/web/server.py`
- Modify: `minder_module_sdk/minder_module_sdk/client.py` (`push_artifact`)
- Test: `tests/test_artifacts_remote_route.py`, extend `minder_module_sdk/tests/test_client.py`

**Interfaces:**
- Consumes: `require_service_principal` (role `module-push`); `ArtifactService.upload_artifact(file_content: bytes, filename, content_length, scope, conversation_id, project_id)` + `get_artifact_service` DI; the session store to resolve `session_id -> conversation_id` (`session.metadata.get("conversation_id")`, pattern from `artifacts_handler.py:70`).
- Produces:
  - Host route `POST /api/artifacts/remote/push` body `{session_id, filename, content_b64, type}` → `{artifact_id}`; resolves the session's `conversation_id`, decodes base64, calls `service.upload_artifact(scope="conversation", conversation_id=…)`.
  - SDK `MinderClient.push_artifact(session_id, filename, content: bytes, type="report") -> int` (base64-encodes, POSTs, returns `artifact_id`).

- [ ] **Step 1: Host route** `minder/web/routes/artifacts_remote.py`:

```python
"""Reverse-push ingress for service-modules to attach an artifact to a session's
conversation. Gated by a Keycloak service principal (module-push)."""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from minder.web.dependencies.service_auth import require_service_principal
from minder.web.routes.artifacts import get_artifact_service
from minder.web.artifact_service import ArtifactService  # adjust import to the real module
from minder.core.context_engineering.history.session_manager import get_session_manager  # real accessor

router = APIRouter(prefix="/api/artifacts/remote", tags=["artifacts"],
                   dependencies=[Depends(require_service_principal)])


class PushArtifactBody(BaseModel):
    session_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content_b64: str = Field(min_length=1)
    type: str = "report"


def _conversation_id_for(session_id: str) -> int:
    session = get_session_manager().get(session_id)  # adjust to the real API
    conv = (getattr(session, "metadata", {}) or {}).get("conversation_id") if session else None
    if not conv:
        raise HTTPException(404, f"session {session_id!r} has no conversation")
    return int(conv)


@router.post("/push")
async def push_artifact(body: PushArtifactBody,
                        service: ArtifactService = Depends(get_artifact_service)) -> dict:
    conversation_id = _conversation_id_for(body.session_id)
    try:
        content = base64.b64decode(body.content_b64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"invalid content_b64: {exc}") from exc
    result = await service.upload_artifact(
        file_content=content, filename=body.filename, content_length=len(content),
        scope="conversation", conversation_id=conversation_id, project_id=None)
    return {"artifact_id": result.get("id") or result.get("artifact_id")}
```

*(The imports for `ArtifactService`, `get_session_manager`, and the `result` id key are marked to be reconciled against the real modules — the implementer greps `minder/web/routes/artifacts.py` for the true `ArtifactService` import + `get_artifact_service`, and `artifacts_handler.py` for how `conversation_id` is read from a session. Use the real names.)*

- [ ] **Step 2: Register the router.** In `minder/web/routes/__init__.py` add `from minder.web.routes.artifacts_remote import router as artifacts_remote_router` + to `__all__`; in `minder/web/server.py` `app.include_router(artifacts_remote_router)`.

- [ ] **Step 3: SDK `push_artifact`** in `client.py`:

```python
    def push_artifact(self, session_id: str, filename: str, content: bytes,
                      type: str = "report") -> int:
        import base64
        payload = {"session_id": session_id, "filename": filename,
                   "content_b64": base64.b64encode(content).decode(), "type": type}
        return self._post("/api/artifacts/remote/push", payload).json()["artifact_id"]
```

- [ ] **Step 4: Tests.**
  - `tests/test_artifacts_remote_route.py`: override `require_service_principal` + `get_artifact_service` (a fake service returning `{"id": 7}`), monkeypatch the session→conversation resolver, POST a small base64 blob, assert 200 + `{"artifact_id": 7}`; and a 404 when the session has no conversation.
  - `minder_module_sdk/tests/test_client.py`: `push_artifact` base64-encodes and returns the id (httpx.post monkeypatched like C1).

---

# Phase D — Manifest, roles

### Task D1: manifest enrichment + `expose_block`

**Files:**
- Modify: `minder_module_sdk/minder_module_sdk/connector.py`
- Test: `minder_module_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Produces: `Connector.expose_block(component_key: str) -> None` (records an extra MF exposed component). `/connector/manifest` `remote.exposed` becomes `{"dashboard": "./Dashboard", <key>: <key> for each exposed block}`; the manifest dict also gains `"card_types": [<unique card_type of tools>]`, `"contract_version": CONTRACT_VERSION`, `"min_core_version": self.min_core_version`.

- [ ] **Step 1: State + method.** In `__init__` add `self._exposed_blocks: list[str] = []` and accept `min_core_version: Optional[str] = None` (store as `self.min_core_version`). Add a module-level `CONTRACT_VERSION = "2"`. Add:

```python
    def expose_block(self, component_key: str) -> None:
        """Declare an extra Module-Federation exposed component (a chat block),
        so the manifest advertises it alongside ./Dashboard."""
        if component_key not in self._exposed_blocks:
            self._exposed_blocks.append(component_key)
```

- [ ] **Step 2: Enrich the manifest route:**

```python
        @app.get("/connector/manifest")
        def manifest() -> dict:
            base = os.environ.get(self._public_base_env, "").rstrip("/")
            remote = None
            if base:
                exposed = {"dashboard": "./Dashboard"}
                exposed.update({k: k for k in self._exposed_blocks})
                remote = {"name": self.name,
                          "remoteEntry": f"{base}/dashboard/remoteEntry.js",
                          "exposed": exposed}
            return {"name": self.name, "display_name": self.display_name,
                    "version": self.version, "tools": self._tool_specs(),
                    "remote": remote,
                    "card_types": sorted({t.card_type for t in self._tools.values() if t.card_type}),
                    "contract_version": CONTRACT_VERSION,
                    "min_core_version": self.min_core_version}
```

- [ ] **Step 3: Test:**

```python
def test_manifest_advertises_exposed_blocks_and_versions(monkeypatch):
    monkeypatch.setenv("MODULE_PUBLIC_BASE", "http://h:9300")
    conn = Connector("m", min_core_version="2")
    conn.expose_block("./MyAnswer")

    @conn.tool("q", card_type="m_answer")
    def q():
        return {}

    from fastapi.testclient import TestClient
    mani = TestClient(conn.asgi()).get("/connector/manifest").json()
    assert mani["remote"]["exposed"] == {"dashboard": "./Dashboard", "./MyAnswer": "./MyAnswer"}
    assert mani["card_types"] == ["m_answer"]
    assert mani["contract_version"] == "2" and mani["min_core_version"] == "2"
```

### Task D2: readiness gating in the reconciler + Keycloak `module-push`

**Files:**
- Modify: `minder/core/modules/registry.py`, `minder/core/modules/watcher.py`, `keycloak/realm-export.json`
- Test: `tests/test_readiness_gating.py`

**Interfaces:**
- Consumes: `ConnectorReconciler.reconcile_once` (polls `/connector/health` + `/connector/manifest`); `RemoteConnector.health()`.
- Produces: reconciler treats a connector as READY only when the connector is healthy AND `health()["ready"]` is not `False`. When `ready is False`, it does NOT call `mark_connector_ready` — it leaves the record `PENDING` (tools stay out of the catalog) and does not count it a health failure.

- [ ] **Step 1: Reconciler check.** In `ConnectorReconciler.reconcile_once`, after fetching the manifest and before `mark_connector_ready`, fetch health and gate:

```python
            health = {}
            try:
                health = conn.health()
            except Exception:  # noqa: BLE001
                health = {}
            if health.get("ready") is False:
                # Alive but not serving yet — keep tools out of the catalog, don't fail.
                continue
            tools = manifest.get("tools") or []
            reg.mark_connector_ready(rec.name, tools)
```

*(Adjust to the real structure of `reconcile_once` from Task 4 of the prior plan — it currently does `fetch_manifest()` + `is_healthy()`. Replace the `is_healthy()` liveness check with a `health()` call and read both `ok`/reachability and `ready`. If `health()` is unreachable → `record_health_failure`; if reachable but `ready is False` → `continue` without marking ready; else `mark_connector_ready`.)*

- [ ] **Step 2: Keycloak.** In `keycloak/realm-export.json`, the `service-account-minder-module` user's `realmRoles` becomes `["module-register", "module-push"]`.

- [ ] **Step 3: Test** (`tests/test_readiness_gating.py`) — a fake connector whose `health()` returns `{"ok": True, "ready": False}` stays PENDING; `{"ok": True, "ready": True}` (with a manifest) goes READY. Mirror the `test_connector_reconciler.py` fake-connector pattern (monkeypatch `watcher.RemoteConnector`).

```python
from minder.core.modules import watcher
from minder.core.modules.registry import ConnectorState, get_registry, reset_registry_for_tests


class _FakeConn:
    def __init__(self, ready):
        self._ready = ready
    def fetch_manifest(self):
        return {"tools": [{"name": "m_q"}]}
    def health(self, timeout=2.0):
        return {"ok": True, "ready": self._ready}
    def is_healthy(self, timeout=2.0):
        return True


def _reg(monkeypatch, tmp_path, ready):
    reset_registry_for_tests()
    monkeypatch.setenv("MINDER_MODULES_DIR", str(tmp_path))
    reg = get_registry()
    reg.register_connector(name="m", connector_url="http://m:9200")
    monkeypatch.setattr(watcher, "RemoteConnector", lambda *a, **k: _FakeConn(ready))
    return reg


def test_not_ready_stays_pending(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path, ready=False)
    watcher.ConnectorReconciler().reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.PENDING


def test_ready_goes_ready(monkeypatch, tmp_path):
    reg = _reg(monkeypatch, tmp_path, ready=True)
    watcher.ConnectorReconciler().reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.READY
```

---

# Phase V — Verify (run once, at the end)

- [ ] **Step 1: SDK unit tests**

Run: `uv run --no-sync pytest minder_module_sdk/tests/ -v`
Expected: all PASS (conn.block/invoke/readiness/params_model/requires_auth/session, MinderClient push/update/remove/push_artifact, manifest).

- [ ] **Step 2: Host unit tests**

Run: `uv run --no-sync pytest tests/test_ctx_identity_forwarding.py tests/test_stream_block_event.py tests/test_readiness_gating.py tests/test_artifacts_remote_route.py tests/test_connector_registry.py tests/test_connector_reconciler.py tests/test_remote_connector.py tests/test_connector_app.py -v`
Expected: all PASS.

- [ ] **Step 3: Full Python suite (no regressions)**

Run: `uv run --no-sync pytest -q --ignore=tests/search/test_enterprise_acl.py --ignore=tests/search/test_stores.py`
Expected: no new failures vs baseline (the pre-existing enterprise-knowledge/qdrant failures are unrelated).

- [ ] **Step 4: Lint**

Run: `uv run --no-sync ruff check minder/ minder_module_sdk/ && uv run --no-sync black --check minder_module_sdk/`
Expected: clean.

- [ ] **Step 5: E2E (with `OPENAI_API_KEY`, per CLAUDE.md)**

1. Run a module (or `maintenance_copilot`) whose tool captures `session_id`, returns immediately, and a daemon thread calls `conn.minder_client().push_block(session_id, "./JobProgress", {"pct": 0})` then `update_block(...)` → confirm a live progress block appears and updates in the chat.
2. Call `minder_client().push_artifact(session_id, "report.txt", b"hello")` → confirm the artifact appears in the conversation.
3. Mark the module `readiness_probe` not-ready at boot → confirm its tools are absent until ready flips true.

- [ ] **Step 6: Commit**

```bash
git add minder/ minder_module_sdk/ keycloak/
git add -f minder_module_sdk/tests/ tests/test_ctx_identity_forwarding.py tests/test_stream_block_event.py tests/test_readiness_gating.py tests/test_artifacts_remote_route.py
git add -f docs/superpowers/plans/2026-07-10-sdk-integration-enhancements.md
git commit -m "feat(sdk): integration enhancements — ergonomics, identity/session, reverse-push, artifacts, manifest"
```

---

## Self-Review Notes

- **Spec coverage:** A1 conn.block · A2 conn.invoke · A3 readiness_probe · A4 params_model · A5 requires_auth · B1–B4 session/principal forwarding · C1 MinderClient blocks · C2 stream block event · C3 artifact push · D1 manifest enrichment · D2 readiness gating + Keycloak module-push. All 10 spec items mapped.
- **Type consistency:** `_Tool` gains `requires_auth` + `params_model` (A4) used in A5; `_call` signature gains `session_id` (B4) used by `invoke` (A2) — A2 notes the dependency; `MinderClient` method names match between `client.py` (C1/C3) and the tests; `ctx.session_id`/`ctx.principal` (B1) consumed in B2/B3.
- **Ordering:** A2's `invoke` uses `_call(..., session_id=…)` which B4 adds — implement B4's `_call` signature change so A2 compiles; both land before Phase V. `_Tool` field additions (A4) precede A5/B4 usage.
- **Known reconcile-against-reality spots (flagged inline):** C3's `ArtifactService` import path, `get_session_manager` accessor, and the upload-result id key must be matched to the real modules (grep `artifacts.py` + `artifacts_handler.py`). D2 adjusts to the real `reconcile_once` shape from the prior plan (health() vs is_healthy()).
