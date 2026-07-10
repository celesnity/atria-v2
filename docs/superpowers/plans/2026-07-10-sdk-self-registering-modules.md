# SDK Self-Registering Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Execution mode is code-all-then-verify (user preference): implement every task in order WITHOUT running tests per-task; write each task's tests alongside its code, then run the whole suite + verification once in the final Phase V.**

**Goal:** Let a service-module register its tools with Atria at runtime (announce on startup, health-gated liveness) so a module appears/disappears live with its container — and never requires editing `atria/**` or `web-ui/**` to add one.

**Architecture:** Keep the file-based `ModuleRegistry` owning the guidance layer (`SKILL.md`, `dir`, presentation manifest, `protected_paths`). Add a parallel connector-liveness table (`PENDING → READY → DOWN`) fed by a Keycloak-authed `POST /api/modules/register` ingress and a `ConnectorReconciler` poll of `GET /connector/manifest` + `/connector/health`. Tool specs come from the live connector manifest, not `manifest.service.tools`. The SDK auto-announces from an ASGI startup hook. web-ui drops the bespoke card path — everything is a generic card or a federated block.

**Tech Stack:** Python 3.12 + FastAPI + PyJWT (Keycloak JWKS, present) + httpx; React 18 + Vite 5 + `@module-federation/runtime`; pytest + Vitest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-10-sdk-self-registering-modules-design.md`.
- **No atria-source edit to add a module** = zero edits to `atria/**` and `web-ui/**`. A module still owns a guidance folder (SKILL.md + presentation manifest + protected_paths); that folder may live outside the repo via `ATRIA_MODULES_DIR`.
- **Two ownership layers:** guidance folder (file-based, may be external) vs connector (runtime self-registered, live tool schemas + liveness). `manifest.service.tools` is documentation-only now; live tool schemas come from `GET /connector/manifest`.
- **Reuse, don't fork:** extend `require_service_principal`, `module_connector.py`, `watcher.py`, `remote.py`; extend the existing `custom_block` `render:"remote"` federated-block contract. Do NOT invent parallel WS types or a second route file.
- **Auth:** `POST /api/modules/register` requires a Keycloak service token with realm role `MODULE_REGISTER_ROLE = "module-register"` (separate from `MODULE_PUSH_ROLE = "module-push"`).
- **Liveness:** connector push-announces once at startup; Atria pull-polls `GET /connector/manifest` + `/connector/health`. `RECONCILE_FAIL_LIMIT = 3` consecutive health failures → `DOWN` → tools leave the catalog live. No persistence of connector state across Atria restarts.
- **URL boundary:** `connector_url` is server→server (Atria reaches it); `remote_entry`/`api_base` are browser-facing (`localhost:<port>`). `api_base = remote_entry.split('/dashboard/')[0]`.
- **SDK never imports `atria`.**
- **Frontend build:** npm (`make build-ui` → `npm ci`/`npm run build`), not pnpm. React/react-dom shared singletons `^18.3.1`.
- **Test command:** `uv run --no-sync pytest <path>` (never bare `pytest`); `npx vitest run <path>` / `npm run build` for web-ui.
- **Commits:** no `Co-Authored-By: Claude` trailer.
- **Plan/spec live under `docs/` which is gitignored — stage them with `git add -f`.**
- **EXECUTION: code all tasks, then Phase V runs all tests + verify once.**

---

## File Structure

**Backend — created:**
- `tests/test_connector_registry.py` — connector-liveness table state machine.
- `tests/test_register_route.py` — `/api/modules/register` auth + reconcile kick.
- `tests/test_connector_reconciler.py` — poll → ready/down + version bump.

**Backend — modified:**
- `atria/core/modules/registry.py` — add the connector-liveness table + API (`register_connector`, `mark_connector_ready`, `mark_connector_down`, `connector_tools`, `live_service_modules`).
- `atria/web/dependencies/service_auth.py` — add `MODULE_REGISTER_ROLE` + `require_module_register` gate (reuse the validation body).
- `atria/web/routes/module_connector.py` — add `POST /api/modules/register` + `POST /api/modules/deregister`.
- `atria/core/modules/watcher.py` — add `ConnectorReconciler` (poll loop) + start/stop hooks.
- `atria/web/server.py` — start/stop the `ConnectorReconciler` in lifespan.
- `atria/core/modules/remote.py` — `build_remote_tool_specs` uses `live_service_modules()` + `connector_tools(name)`.
- `atria/core/context_engineering/tools/registry.py:131` — feed `live_service_modules()` instead of `.all()`.
- `keycloak/realm-export.json` — add realm role `module-register` + a `atria-module` confidential client with service accounts.

**SDK — created:**
- `atria_module_sdk/atria_module_sdk/announce.py` — startup/shutdown announce + Keycloak client-credentials token.

**SDK — modified:**
- `atria_module_sdk/atria_module_sdk/connector.py` (or the module where `Connector`/`asgi()` lives) — wire announce into ASGI lifespan; add `block(...)` helper.
- `atria_module_sdk/__init__.py` — export `block`.

**Frontend — modified:**
- `web-ui/src/lib/cardRegistry.ts` — drop bespoke `CARD_MAPPERS` entries (generic + federated only).
- `web-ui/src/components/Chat/MessageList.tsx` — remove the `maintenance_answer` branch.

**Module (`maintenance_copilot`) — modified:**
- `modules/maintenance_copilot/backend/app.py` — return `blocks:[conn.block("MaintenanceAnswer", ...)]` instead of `card_type:"maintenance_answer"`.
- `modules/maintenance_copilot/frontend/src/` — expose a `MaintenanceAnswer` block component (port `MaintenanceAnswerBlock.tsx`).
- Delete `web-ui/src/components/Chat/MaintenanceAnswer/MaintenanceAnswerBlock.tsx` once the module owns it.

---

# Phase 1 — Core: connector-liveness table

### Task 1: connector-liveness table in `ModuleRegistry`

**Files:**
- Modify: `atria/core/modules/registry.py`
- Test: `tests/test_connector_registry.py`

**Interfaces:**
- Consumes: existing `ModuleRegistry` (folder-scan, `version`, `all()`, `get(name)`).
- Produces:
  - `class ConnectorState(str, Enum)`: `PENDING="pending"`, `READY="ready"`, `DOWN="down"`.
  - `@dataclass ConnectorRecord`: `name: str`, `connector_url: str`, `remote_entry: Optional[str]`, `api_base: Optional[str]`, `state: ConnectorState`, `tools: List[dict]` (default `[]`), `fail_count: int` (default `0`), `last_seen: float` (default `0.0`).
  - On `ModuleRegistry`: `register_connector(*, name, connector_url, remote_entry=None, api_base=None) -> None` (upsert `PENDING`, bump version), `mark_connector_ready(name, tools: List[dict]) -> None` (set `READY`, replace tools, reset `fail_count`, bump version only if state or tools changed), `mark_connector_down(name) -> None` (set `DOWN`, bump version if state changed), `record_health_failure(name) -> None` (increment `fail_count`; if `>= RECONCILE_FAIL_LIMIT` call `mark_connector_down`), `connector_records() -> List[ConnectorRecord]`, `connector_tools(name) -> List[dict]` (`READY` tools else `[]`), `live_service_modules() -> List[Module]` (guidance `Module`s whose connector is `READY`; connectors with no matching folder are excluded here — they surface via a separate tools-only path in Task 5).
  - Module constant: `RECONCILE_FAIL_LIMIT = 3`.

- [ ] **Step 1: Add enum, record, and constant** near the top of `atria/core/modules/registry.py` (after the existing imports add `from dataclasses import dataclass, field`, `from enum import Enum`, `from typing import Optional`):

```python
RECONCILE_FAIL_LIMIT = 3


class ConnectorState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    DOWN = "down"


@dataclass
class ConnectorRecord:
    name: str
    connector_url: str
    remote_entry: Optional[str] = None
    api_base: Optional[str] = None
    state: ConnectorState = ConnectorState.PENDING
    tools: List[dict] = field(default_factory=list)
    fail_count: int = 0
    last_seen: float = 0.0
```

- [ ] **Step 2: Add the connector table to `ModuleRegistry.__init__`** — extend the existing `__init__` body:

```python
    def __init__(self, root: Path):
        self.root = root
        self._modules: Dict[str, Module] = {}
        self._connectors: Dict[str, ConnectorRecord] = {}
        self._version: int = 0
        self._lock = threading.Lock()
```

- [ ] **Step 3: Add the connector API methods** to `ModuleRegistry` (place after `get`):

```python
    def register_connector(self, *, name: str, connector_url: str,
                           remote_entry: Optional[str] = None,
                           api_base: Optional[str] = None) -> None:
        """Runtime announce: upsert a PENDING connector record and bump version."""
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None:
                rec = ConnectorRecord(name=name, connector_url=connector_url)
                self._connectors[name] = rec
            rec.connector_url = connector_url
            rec.remote_entry = remote_entry
            rec.api_base = api_base
            rec.state = ConnectorState.PENDING
            rec.fail_count = 0
            self._version += 1

    def mark_connector_ready(self, name: str, tools: List[dict]) -> None:
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None:
                return
            changed = rec.state != ConnectorState.READY or rec.tools != tools
            rec.state = ConnectorState.READY
            rec.tools = list(tools)
            rec.fail_count = 0
            if changed:
                self._version += 1

    def mark_connector_down(self, name: str) -> None:
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None or rec.state == ConnectorState.DOWN:
                return
            rec.state = ConnectorState.DOWN
            self._version += 1

    def record_health_failure(self, name: str) -> None:
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None:
                return
            rec.fail_count += 1
            over_limit = rec.fail_count >= RECONCILE_FAIL_LIMIT
        if over_limit:
            self.mark_connector_down(name)

    def connector_records(self) -> List[ConnectorRecord]:
        with self._lock:
            return [self._connectors[n] for n in sorted(self._connectors)]

    def connector_tools(self, name: str) -> List[dict]:
        with self._lock:
            rec = self._connectors.get(name)
            return list(rec.tools) if rec and rec.state == ConnectorState.READY else []

    def live_service_modules(self) -> List[Module]:
        """Guidance Modules whose connector is READY (agent tool-builder input)."""
        with self._lock:
            ready = {n for n, r in self._connectors.items() if r.state == ConnectorState.READY}
            return [self._modules[n] for n in sorted(self._modules) if n in ready]
```

- [ ] **Step 4: Write the test** `tests/test_connector_registry.py`:

```python
from atria.core.modules.registry import (
    ConnectorState,
    ModuleRegistry,
    RECONCILE_FAIL_LIMIT,
)


def _reg(tmp_path):
    (tmp_path / "m").mkdir()
    return ModuleRegistry(tmp_path)


def test_register_connector_is_pending_and_bumps_version(tmp_path):
    reg = _reg(tmp_path)
    v0 = reg.version
    reg.register_connector(name="m", connector_url="http://m:9200")
    assert reg.version == v0 + 1
    rec = reg.connector_records()[0]
    assert rec.state is ConnectorState.PENDING
    assert reg.connector_tools("m") == []  # not READY yet


def test_mark_ready_exposes_tools_and_bumps_on_change(tmp_path):
    reg = _reg(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    v1 = reg.version
    tools = [{"name": "m_query", "parameters": {"type": "object"}}]
    reg.mark_connector_ready("m", tools)
    assert reg.version == v1 + 1
    assert reg.connector_tools("m") == tools
    # Idempotent: same tools + state → no version bump.
    v2 = reg.version
    reg.mark_connector_ready("m", tools)
    assert reg.version == v2


def test_health_failures_flip_to_down_and_hide_tools(tmp_path):
    reg = _reg(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready("m", [{"name": "m_query"}])
    for _ in range(RECONCILE_FAIL_LIMIT):
        reg.record_health_failure("m")
    rec = reg.connector_records()[0]
    assert rec.state is ConnectorState.DOWN
    assert reg.connector_tools("m") == []


def test_live_service_modules_tracks_ready_state(tmp_path):
    reg = _reg(tmp_path)
    reg._modules["m"] = object()  # stand-in guidance Module keyed by name
    reg.register_connector(name="m", connector_url="http://m:9200")
    assert reg.live_service_modules() == []          # PENDING → not live
    reg.mark_connector_ready("m", [])
    assert reg.live_service_modules() == [reg._modules["m"]]
    reg.mark_connector_down("m")
    assert reg.live_service_modules() == []
```

*(Executed in Phase V.)*

---

# Phase 2 — Core: register ingress + Keycloak role

### Task 2: `require_module_register` service-auth gate

**Files:**
- Modify: `atria/web/dependencies/service_auth.py`
- Test: `tests/test_register_route.py` (written in Task 3; the gate is exercised there)

**Interfaces:**
- Consumes: existing token validation flow in `require_service_principal`.
- Produces: `MODULE_REGISTER_ROLE = "module-register"`; `async def require_module_register(request: Request) -> dict` — same validation as `require_service_principal` but requires `MODULE_REGISTER_ROLE`.

- [ ] **Step 1: Refactor the shared validation into a helper and add the new gate.** Replace the body of `service_auth.py` role-check tail with a shared `_validate_and_roles` and two gates:

```python
MODULE_PUSH_ROLE = "module-push"
MODULE_REGISTER_ROLE = "module-register"


async def _validate_and_roles(request: Request) -> tuple[dict, list[str]]:
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
    return claims, roles


def _principal(claims: dict, roles: list[str]) -> dict:
    return {"client_id": claims.get("azp") or claims.get("clientId"), "roles": roles}


async def require_service_principal(request: Request) -> dict:
    claims, roles = await _validate_and_roles(request)
    if MODULE_PUSH_ROLE not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing {MODULE_PUSH_ROLE} role")
    return _principal(claims, roles)


async def require_module_register(request: Request) -> dict:
    claims, roles = await _validate_and_roles(request)
    if MODULE_REGISTER_ROLE not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing {MODULE_REGISTER_ROLE} role")
    return _principal(claims, roles)
```

- [ ] **Step 2: Add the Keycloak role + client** in `keycloak/realm-export.json`. Under `"roles": { "realm": [ ... ] }` add `{ "name": "module-register", "description": "May self-register a service-module connector" }`. Under `"clients": [ ... ]` add a confidential service-account client:

```jsonc
{
  "clientId": "atria-module",
  "name": "Atria Service Module",
  "enabled": true,
  "publicClient": false,
  "serviceAccountsEnabled": true,
  "standardFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "secret": "change-me-in-deploy",
  "serviceAccountClientRoles": {},
  "serviceAccountRealmRoles": ["module-register"]
}
```

*(Note: existing realm exports may express service-account role grants differently; match the surrounding schema. If the export lists a separate `serviceAccountRealmRoles` block per client, follow that shape.)*

### Task 3: `POST /api/modules/register` + `/deregister`

**Files:**
- Modify: `atria/web/routes/module_connector.py`
- Test: `tests/test_register_route.py`

**Interfaces:**
- Consumes: `require_module_register` (Task 2); `get_registry()` with `register_connector` (Task 1); `ConnectorReconciler.reconcile_once` (Task 4) via a module-level hook — for now expose a thin `_kick_reconcile(name)` that calls the reconciler if started, else no-ops.
- Produces: routes `POST /api/modules/register` (body `RegisterBody`) → `{"ok": true}`; `POST /api/modules/deregister` (body `{module}`) → 204.

- [ ] **Step 1: Add request models + routes** to `atria/web/routes/module_connector.py` (add imports: `from pydantic import BaseModel, Field`; `from typing import Optional`; `from atria.web.dependencies.service_auth import require_module_register`; `from atria.core.modules.watcher import kick_reconcile`):

```python
class RegisterBody(BaseModel):
    module: str = Field(min_length=1)
    connector_url: str = Field(min_length=1)
    remote_entry: Optional[str] = None
    api_base: Optional[str] = None


class DeregisterBody(BaseModel):
    module: str = Field(min_length=1)


@router.post("/register")
def register_connector(body: RegisterBody, _svc=Depends(require_module_register)) -> dict:
    """Runtime self-registration of a module connector. Health-poll takes over."""
    get_registry().register_connector(
        name=body.module,
        connector_url=body.connector_url,
        remote_entry=body.remote_entry,
        api_base=body.api_base,
    )
    kick_reconcile(body.module)  # reconcile now rather than waiting a poll cycle
    return {"ok": True}


@router.post("/deregister", status_code=204)
def deregister_connector(body: DeregisterBody, _svc=Depends(require_module_register)) -> None:
    get_registry().mark_connector_down(body.module)
```

- [ ] **Step 2: Write the test** `tests/test_register_route.py`. Override the auth dependency (this is the established FastAPI pattern) and assert the registry is updated + reconcile kicked:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from atria.core.modules.registry import ConnectorState, reset_registry_for_tests, get_registry
from atria.web.dependencies.service_auth import require_module_register
from atria.web.routes.module_connector import router


@pytest.fixture
def client(monkeypatch, tmp_path):
    reset_registry_for_tests()
    monkeypatch.setenv("ATRIA_MODULES_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_module_register] = lambda: {"client_id": "atria-module", "roles": ["module-register"]}
    return TestClient(app)


def test_register_creates_pending_connector(client):
    r = client.post("/api/modules/register", json={
        "module": "m", "connector_url": "http://m:9200",
        "remote_entry": "http://localhost:9200/dashboard/remoteEntry.js",
    })
    assert r.status_code == 200 and r.json() == {"ok": True}
    rec = get_registry().connector_records()[0]
    assert rec.name == "m" and rec.state is ConnectorState.PENDING


def test_deregister_marks_down(client):
    client.post("/api/modules/register", json={"module": "m", "connector_url": "http://m:9200"})
    get_registry().mark_connector_ready("m", [{"name": "m_q"}])
    r = client.post("/api/modules/deregister", json={"module": "m"})
    assert r.status_code == 204
    assert get_registry().connector_records()[0].state is ConnectorState.DOWN
```

*(A 403-without-role case is covered by not overriding the dependency in a separate test if Keycloak is wired in CI; with no validator configured the gate returns 503, which the test suite treats as "auth enforced".)*

---

# Phase 3 — Core: reconciler, tool wiring, server lifespan

### Task 4: `ConnectorReconciler` poll loop

**Files:**
- Modify: `atria/core/modules/watcher.py`
- Test: `tests/test_connector_reconciler.py`

**Interfaces:**
- Consumes: `get_registry()` (`connector_records`, `mark_connector_ready`, `record_health_failure`); `RemoteConnector.fetch_manifest`, `RemoteConnector.is_healthy` from `atria/core/modules/remote.py`.
- Produces:
  - `class ConnectorReconciler` with `reconcile_once(name: Optional[str] = None) -> None`, `start()`, `stop()`, poll interval `RECONCILE_INTERVAL_SEC = 5.0`.
  - Module-level: `start_connector_reconciler()`, `stop_connector_reconciler()`, `kick_reconcile(name: str)` (thread-safe no-op if reconciler not started).
  - Tool-spec parsing: a connector manifest from `fetch_manifest()` is expected to be `{"tools": [ {name, description, parameters}, ... ]}` — extract `tools`.

- [ ] **Step 1: Add the reconciler** to `atria/core/modules/watcher.py` (add imports `import threading`, `import time`, `from typing import Optional`, `from atria.core.modules.registry import get_registry`, `from atria.core.modules.remote import RemoteConnector`):

```python
RECONCILE_INTERVAL_SEC = 5.0


class ConnectorReconciler:
    """Poll every registered connector: refresh live tool schemas + liveness."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def reconcile_once(self, name: Optional[str] = None) -> None:
        reg = get_registry()
        for rec in reg.connector_records():
            if name is not None and rec.name != name:
                continue
            conn = RemoteConnector(rec.name, rec.connector_url)
            manifest = None
            try:
                manifest = conn.fetch_manifest()
            except Exception:  # noqa: BLE001 — network failure == unhealthy
                manifest = None
            if manifest is None or not conn.is_healthy():
                reg.record_health_failure(rec.name)
                continue
            tools = manifest.get("tools") or []
            reg.mark_connector_ready(rec.name, tools)

    def _run(self) -> None:
        while not self._stop.wait(RECONCILE_INTERVAL_SEC):
            try:
                self.reconcile_once()
            except Exception:  # noqa: BLE001 — never let the loop die
                logger.exception("connector reconcile pass failed")

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="connector-reconciler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None


_RECONCILER: Optional[ConnectorReconciler] = None


def start_connector_reconciler() -> None:
    global _RECONCILER
    if _RECONCILER is None:
        _RECONCILER = ConnectorReconciler()
        _RECONCILER.start()


def stop_connector_reconciler() -> None:
    global _RECONCILER
    if _RECONCILER is not None:
        _RECONCILER.stop()
        _RECONCILER = None


def kick_reconcile(name: str) -> None:
    """Reconcile a single connector immediately (called from the register route)."""
    if _RECONCILER is not None:
        _RECONCILER.reconcile_once(name)
```

- [ ] **Step 2: Confirm `RemoteConnector` accepts a 2-arg construction.** In `atria/core/modules/remote.py`, `RemoteConnector.__init__(self, name, connector_url, health_path="/connector/health", ...)` — `health_path` already defaults, so `RemoteConnector(rec.name, rec.connector_url)` is valid. No change needed; note it here so the implementer does not add a param.

- [ ] **Step 3: Write the test** `tests/test_connector_reconciler.py` (stub `RemoteConnector` via monkeypatch):

```python
from atria.core.modules import watcher
from atria.core.modules.registry import (
    ConnectorState, ModuleRegistry, RECONCILE_FAIL_LIMIT, reset_registry_for_tests,
)


class _FakeConn:
    def __init__(self, manifest, healthy):
        self._manifest, self._healthy = manifest, healthy
    def fetch_manifest(self):
        return self._manifest
    def is_healthy(self, timeout=2.0):
        return self._healthy


def _install(monkeypatch, tmp_path, manifest, healthy):
    reset_registry_for_tests()
    monkeypatch.setenv("ATRIA_MODULES_DIR", str(tmp_path))
    from atria.core.modules import registry as reg_mod
    reg = reg_mod.get_registry()
    reg.register_connector(name="m", connector_url="http://m:9200")
    monkeypatch.setattr(watcher, "RemoteConnector",
                        lambda *a, **k: _FakeConn(manifest, healthy))
    return reg


def test_reconcile_marks_ready_with_live_tools(monkeypatch, tmp_path):
    tools = [{"name": "m_q", "parameters": {"type": "object"}}]
    reg = _install(monkeypatch, tmp_path, {"tools": tools}, healthy=True)
    watcher.ConnectorReconciler().reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.READY
    assert reg.connector_tools("m") == tools


def test_repeated_unhealthy_polls_go_down(monkeypatch, tmp_path):
    reg = _install(monkeypatch, tmp_path, None, healthy=False)
    r = watcher.ConnectorReconciler()
    for _ in range(RECONCILE_FAIL_LIMIT):
        r.reconcile_once("m")
    assert reg.connector_records()[0].state is ConnectorState.DOWN
```

### Task 5: tool-spec build uses live connector tools

**Files:**
- Modify: `atria/core/modules/remote.py` (`build_remote_tool_specs`)
- Modify: `atria/core/context_engineering/tools/registry.py:131`
- Test: `tests/test_remote_registry_wiring.py` (extend existing)

**Interfaces:**
- Consumes: `get_registry().live_service_modules()`, `get_registry().connector_tools(name)`, `get_registry().connector_records()`.
- Produces: `build_remote_tool_specs(ctx, modules)` builds one `ToolSpec` per tool in the module's *live* `connector_tools`, using the connector record's `connector_url` for the `RemoteConnector`. Modules with a `READY` connector but no guidance folder still contribute tools (tools-only path).

- [ ] **Step 1: Rewrite `build_remote_tool_specs`** in `atria/core/modules/remote.py` to source tools + URL from the connector table:

```python
def build_remote_tool_specs(ctx: "SkillToolContext",
                            modules: "list[Module]") -> "list[ToolSpec]":
    """Build proxy ToolSpecs for every READY service-module connector, from its
    live ``/connector/manifest`` tool schemas (not the committed manifest)."""
    from atria.core.skill_tools import ToolSpec  # local import: avoid cycle at module load
    from atria.core.modules.registry import get_registry, ConnectorState

    reg = get_registry()
    specs: list[ToolSpec] = []
    for rec in reg.connector_records():
        if rec.state is not ConnectorState.READY:
            continue
        conn = RemoteConnector(rec.name, rec.connector_url)
        for tool in rec.tools:
            name = tool.get("name")
            if not name:
                continue
            specs.append(ToolSpec(
                name=name,
                description=tool.get("description", ""),
                parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                handler=_make_handler(ctx, conn, name),
            ))
    return specs
```

*(The `modules` argument is retained for signature compatibility but is no longer the tool source; callers may pass `live_service_modules()`.)*

- [ ] **Step 2: Update the tool-registry call site** `atria/core/context_engineering/tools/registry.py:131`:

```python
            from atria.core.modules.remote import build_remote_tool_specs
            _mod_reg = _get_mod_registry()
            _remote_specs = build_remote_tool_specs(self.skill_ctx, _mod_reg.live_service_modules())
```

- [ ] **Step 3: Extend** `tests/test_remote_registry_wiring.py` with a case proving a `READY` connector yields tool specs and a `DOWN`/`PENDING` one yields none:

```python
def test_build_specs_only_for_ready_connectors(monkeypatch, tmp_path):
    from atria.core.modules.registry import reset_registry_for_tests, get_registry
    from atria.core.modules.remote import build_remote_tool_specs
    reset_registry_for_tests()
    monkeypatch.setenv("ATRIA_MODULES_DIR", str(tmp_path))
    reg = get_registry()
    reg.register_connector(name="m", connector_url="http://m:9200")
    # PENDING → no specs
    assert build_remote_tool_specs(_ctx(), reg.live_service_modules()) == []
    reg.mark_connector_ready("m", [{"name": "m_q", "parameters": {"type": "object"}}])
    specs = build_remote_tool_specs(_ctx(), reg.live_service_modules())
    assert [s.name for s in specs] == ["m_q"]
```

*(Reuse or add a minimal `_ctx()` helper mirroring the existing test's context construction.)*

### Task 6: start/stop reconciler in server lifespan

**Files:**
- Modify: `atria/web/server.py`

**Interfaces:**
- Consumes: `start_connector_reconciler`, `stop_connector_reconciler` (Task 4).

- [ ] **Step 1: Import and start** near the existing `start_global_watcher(...)` call (~line 119):

```python
    from atria.core.modules.watcher import (
        start_global_watcher, stop_global_watcher,
        start_connector_reconciler, stop_connector_reconciler,
    )
    start_global_watcher(on_change=_broadcast_modules_changed)
    start_connector_reconciler()
```

- [ ] **Step 2: Stop it** alongside the existing `stop_global_watcher()` (~line 219):

```python
        stop_global_watcher()
        stop_connector_reconciler()
```

*(If `server.py` imports `start_global_watcher`/`stop_global_watcher` at module top rather than inline, add the two new names to that existing import instead of a local import.)*

---

# Phase 4 — SDK: auto-announce + block helper

### Task 7: `announce.py` — startup/shutdown announce

**Files:**
- Create: `atria_module_sdk/atria_module_sdk/announce.py`

**Interfaces:**
- Produces:
  - `def resolve_announce_config() -> Optional[AnnounceConfig]` — reads env `ATRIA_URL`, `ATRIA_MODULE_CONNECTOR_URL` (server-reachable self URL), `ATRIA_MODULE_REMOTE_ENTRY`, `KEYCLOAK_TOKEN_URL`, `ATRIA_MODULE_CLIENT_ID` (default `"atria-module"`), `ATRIA_MODULE_CLIENT_SECRET`. Returns `None` (announce disabled) if `ATRIA_URL` or `ATRIA_MODULE_CONNECTOR_URL` is missing.
  - `@dataclass AnnounceConfig`: `atria_url, connector_url, remote_entry, api_base, token_url, client_id, client_secret`.
  - `def fetch_service_token(cfg) -> Optional[str]` — client-credentials grant; `None` if no `token_url`/secret (dev/no-auth).
  - `def announce(module: str, cfg: AnnounceConfig) -> None` — `POST {atria_url}/api/modules/register` with bearer token.
  - `def deregister(module: str, cfg: AnnounceConfig) -> None` — `POST {atria_url}/api/modules/deregister`, best-effort (swallow errors).

- [ ] **Step 1: Implement** `atria_module_sdk/atria_module_sdk/announce.py`:

```python
"""Runtime self-registration: announce this connector to Atria on startup.

Never imports ``atria``. Uses only ``httpx`` + env config.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("atria_module_sdk.announce")


@dataclass
class AnnounceConfig:
    atria_url: str
    connector_url: str
    remote_entry: Optional[str]
    api_base: Optional[str]
    token_url: Optional[str]
    client_id: str
    client_secret: Optional[str]


def resolve_announce_config() -> Optional[AnnounceConfig]:
    atria_url = os.environ.get("ATRIA_URL")
    connector_url = os.environ.get("ATRIA_MODULE_CONNECTOR_URL")
    if not atria_url or not connector_url:
        logger.info("announce disabled (ATRIA_URL / ATRIA_MODULE_CONNECTOR_URL unset)")
        return None
    remote_entry = os.environ.get("ATRIA_MODULE_REMOTE_ENTRY")
    api_base = remote_entry.split("/dashboard/")[0] if remote_entry else None
    return AnnounceConfig(
        atria_url=atria_url.rstrip("/"),
        connector_url=connector_url.rstrip("/"),
        remote_entry=remote_entry,
        api_base=api_base,
        token_url=os.environ.get("KEYCLOAK_TOKEN_URL"),
        client_id=os.environ.get("ATRIA_MODULE_CLIENT_ID", "atria-module"),
        client_secret=os.environ.get("ATRIA_MODULE_CLIENT_SECRET"),
    )


def fetch_service_token(cfg: AnnounceConfig) -> Optional[str]:
    if not cfg.token_url or not cfg.client_secret:
        return None
    resp = httpx.post(cfg.token_url, data={
        "grant_type": "client_credentials",
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
    }, timeout=10.0)
    resp.raise_for_status()
    return resp.json().get("access_token")


def announce(module: str, cfg: AnnounceConfig) -> None:
    headers = {}
    token = fetch_service_token(cfg)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = httpx.post(f"{cfg.atria_url}/api/modules/register", json={
        "module": module,
        "connector_url": cfg.connector_url,
        "remote_entry": cfg.remote_entry,
        "api_base": cfg.api_base,
    }, headers=headers, timeout=10.0)
    resp.raise_for_status()
    logger.info("announced module %s to %s", module, cfg.atria_url)


def deregister(module: str, cfg: AnnounceConfig) -> None:
    try:
        headers = {}
        token = fetch_service_token(cfg)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        httpx.post(f"{cfg.atria_url}/api/modules/deregister",
                   json={"module": module}, headers=headers, timeout=5.0)
    except Exception as exc:  # noqa: BLE001 — best-effort on shutdown
        logger.warning("deregister failed for %s: %s", module, exc)
```

### Task 8: wire announce into `Connector.asgi()` + add `block()` helper

**Files:**
- Modify: the SDK module defining `Connector` / `asgi()` / `card` (locate with `grep -rn "def asgi\|def card\|class Connector" atria_module_sdk`).
- Modify: `atria_module_sdk/atria_module_sdk/__init__.py` (export `block`).

**Interfaces:**
- Consumes: `resolve_announce_config`, `announce`, `deregister` (Task 7).
- Produces:
  - `Connector.asgi()` registers FastAPI/Starlette `startup` and `shutdown` handlers that call `announce(self.name, cfg)` / `deregister(self.name, cfg)` when `resolve_announce_config()` is non-`None`.
  - `def block(component, props=None, *, remote_name, remote_entry, height="auto", title=None) -> dict` returning the federated descriptor: `{"render": "remote", "remote_name", "remote_entry", "component", "props", "api_base": remote_entry.split('/dashboard/')[0], "height", "title"}`.

- [ ] **Step 1: Add the announce hooks** inside `asgi()`, after the app is built and before `return app`:

```python
        from atria_module_sdk.announce import resolve_announce_config, announce, deregister

        @app.on_event("startup")
        def _atria_announce() -> None:
            cfg = resolve_announce_config()
            if cfg is not None:
                try:
                    announce(self.name, cfg)
                except Exception as exc:  # noqa: BLE001 — don't crash the module on a flaky Atria
                    import logging
                    logging.getLogger("atria_module_sdk").warning("announce failed: %s", exc)

        @app.on_event("shutdown")
        def _atria_deregister() -> None:
            cfg = resolve_announce_config()
            if cfg is not None:
                deregister(self.name, cfg)
```

- [ ] **Step 2: Add the `block()` helper** next to `card()` in the same module:

```python
def block(component, props=None, *, remote_name, remote_entry, height="auto", title=None):
    """Federated chat-block descriptor matching Atria's ``custom_block`` render:'remote'."""
    return {
        "render": "remote",
        "remote_name": remote_name,
        "remote_entry": remote_entry,
        "component": component,
        "props": props or {},
        "api_base": remote_entry.split("/dashboard/")[0],
        "height": height,
        "title": title,
    }
```

- [ ] **Step 3: Export it** in `atria_module_sdk/__init__.py` — add `block` to the existing `from .connector import ... , card` line and to `__all__`.

*(No SDK unit test is mandated here — the SDK is exercised end-to-end in Phase V via `maintenance_copilot`. If the SDK has an existing test file, add a `test_block_descriptor` asserting `block("X", {"a":1}, remote_name="m", remote_entry="http://h/dashboard/remoteEntry.js")["api_base"] == "http://h"`.)*

---

# Phase 5 — web-ui: kill bespoke cards + migrate maintenance

### Task 9: drop the bespoke card path

**Files:**
- Modify: `web-ui/src/lib/cardRegistry.ts`
- Modify: `web-ui/src/components/Chat/MessageList.tsx`

**Interfaces:**
- Produces: `CARD_MAPPERS` becomes `{}` (empty); `mapCard` still falls back to `mapModuleCard`; `isCardType` still true for `*_card`. `MessageList` no longer branches on `maintenance_answer`.

- [ ] **Step 1: Empty the bespoke registry** in `cardRegistry.ts` — remove the `mapMaintenanceAnswer` import and the entry:

```typescript
export const CARD_MAPPERS: Record<string, CardMapper> = {};
```

- [ ] **Step 2: Remove the `maintenance_answer` branch** in `MessageList.tsx` (delete line `if (message.role === 'maintenance_answer') return <MaintenanceAnswerBlock message={message} />;` and its import). The `module_card` (generic) and `custom_block` `render:"remote"` (federated) branches remain and cover all modules.

- [ ] **Step 3: Update `cardRegistry.test.ts`** (if present) to assert `CARD_MAPPERS` is empty and `mapCard('maintenance_answer', {...})` returns a `module_card` role via the generic fallback. If no such test exists, add `web-ui/src/lib/cardRegistry.test.ts` with that assertion.

### Task 10: `maintenance_copilot` ships its answer block

**Files:**
- Modify: `modules/maintenance_copilot/frontend/src/` (add `MaintenanceAnswer` exposed component; port `web-ui/src/components/Chat/MaintenanceAnswer/MaintenanceAnswerBlock.tsx` into the module, adapting props to the block descriptor's `props`).
- Modify: `modules/maintenance_copilot/frontend/vite.config.ts` — add `MaintenanceAnswer: './src/MaintenanceAnswer'` to the MF `exposes` map (keep `react`/`react-dom` singletons).
- Modify: `modules/maintenance_copilot/backend/app.py` — tool handler returns `{"output": text, "blocks": [conn.block("MaintenanceAnswer", answer_props, remote_name="maintenance_copilot", remote_entry=os.environ["ATRIA_MODULE_REMOTE_ENTRY"])]}` instead of `card_type`.
- Delete: `web-ui/src/components/Chat/MaintenanceAnswer/MaintenanceAnswerBlock.tsx` and its folder once the module owns the component.

**Interfaces:**
- Consumes: `conn.block(...)` (Task 8); the federated-block `render:"remote"` render path already in `MessageList` (`RemoteBlock`).

- [ ] **Step 1: Port the component.** Copy `MaintenanceAnswerBlock.tsx`'s JSX into `modules/maintenance_copilot/frontend/src/MaintenanceAnswer.tsx` as `export default function MaintenanceAnswer(props)`, where `props` is the answer object the backend passes (answer text, confidence band, citations, warnings). Drop the `message`-shaped wrapper — the block receives raw props.

- [ ] **Step 2: Expose it** in `modules/maintenance_copilot/frontend/vite.config.ts`:

```typescript
      exposes: {
        './Dashboard': './src/DashboardApp',
        './MaintenanceAnswer': './src/MaintenanceAnswer',
      },
```

- [ ] **Step 3: Emit the block** in `modules/maintenance_copilot/backend/app.py`. Replace the `card_type="maintenance_answer"` return with:

```python
    remote_entry = os.environ.get("ATRIA_MODULE_REMOTE_ENTRY", "")
    return {
        "output": answer["text"],
        "blocks": [conn.block(
            "MaintenanceAnswer",
            {"answer": answer["text"], "confidence_band": answer["band"],
             "citations": answer["citations"], "validation_warnings": answer["warnings"]},
            remote_name="maintenance_copilot",
            remote_entry=remote_entry,
        )],
    }
```

*(Match the real field names in the existing handler; the shape above is illustrative of the mapping, not new fields.)*

- [ ] **Step 4: Delete the host-side component** `web-ui/src/components/Chat/MaintenanceAnswer/` and remove any remaining imports of it (`grep -rn MaintenanceAnswer web-ui/src`).

---

# Phase V — Verify (run once, at the end)

- [ ] **Step 1: Python unit tests**

Run: `uv run --no-sync pytest tests/test_connector_registry.py tests/test_register_route.py tests/test_connector_reconciler.py tests/test_remote_registry_wiring.py tests/test_remote_connector.py tests/test_connector_app.py -v`
Expected: all PASS.

- [ ] **Step 2: Full Python suite (no regressions)**

Run: `uv run --no-sync pytest -q`
Expected: no new failures vs the branch baseline.

- [ ] **Step 3: web-ui tests + build**

Run: `cd web-ui && npx vitest run src/lib/cardRegistry.test.ts src/components/Chat/RemoteBlock.test.tsx && npm run build`
Expected: PASS + clean build (no dangling `MaintenanceAnswerBlock` import).

- [ ] **Step 4: SDK block descriptor sanity**

Run: `uv run --no-sync python -c "from atria_module_sdk import block; d=block('X',{'a':1},remote_name='m',remote_entry='http://h/dashboard/remoteEntry.js'); assert d['render']=='remote' and d['api_base']=='http://h', d; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: End-to-end (per CLAUDE.md — real API, `OPENAI_API_KEY` set)**

1. Start Atria web (`make run` / the web server) with Keycloak configured (or auth-disabled dev mode).
2. Run the `maintenance_copilot` connector with `ATRIA_URL`, `ATRIA_MODULE_CONNECTOR_URL`, `ATRIA_MODULE_REMOTE_ENTRY` set (`atria-module dev maintenance_copilot`).
3. Confirm `POST /api/modules/register` is received; within one reconcile cycle the `maintenance_copilot_query` tool appears in the agent tool list.
4. Ask a maintenance question in chat → agent calls the tool → the `MaintenanceAnswer` federated block renders natively (no bespoke card).
5. Kill the connector container → after `RECONCILE_FAIL_LIMIT` polls the tool disappears from the catalog; a mid-flight call fails closed with the low-confidence card.

- [ ] **Step 6: Commit**

```bash
git add atria/ atria_module_sdk/ web-ui/ modules/maintenance_copilot/ keycloak/ tests/
git add -f docs/superpowers/plans/2026-07-10-sdk-self-registering-modules.md
git commit -m "feat(modules): SDK runtime self-registration + live connector discovery; kill bespoke cards"
```

*(No `Co-Authored-By: Claude` trailer.)*

---

## Self-Review Notes

- **Spec coverage:** registry connector table (Task 1) · register ingress + role (Tasks 2–3) · reconciler + tool wiring + lifespan (Tasks 4–6) · SDK announce + `block()` (Tasks 7–8) · kill bespoke cards + maintenance federated block (Tasks 9–10) · verify incl. live disappear (Phase V). All five spec "Core decisions" map to tasks.
- **Type consistency:** `register_connector` / `mark_connector_ready` / `mark_connector_down` / `record_health_failure` / `connector_records` / `connector_tools` / `live_service_modules` used identically across Tasks 1, 3, 4, 5. `RECONCILE_FAIL_LIMIT` (registry) and `RECONCILE_INTERVAL_SEC` (watcher) are distinct constants in distinct modules. `block(...)` descriptor keys match the SDK export (Task 8) and the emit site (Task 10).
- **Guidance-folder boundary:** `maintenance_copilot`'s folder stays; only `manifest.service.tools` stops being the schema source and `card_type` becomes a `block`. No `atria/**` or `web-ui/**` edit is needed to add a *future* module.
- **Known illustrative spots:** the Keycloak client JSON (Task 2) and the maintenance handler field names (Task 10) must match the real surrounding schema/handler — flagged inline.
