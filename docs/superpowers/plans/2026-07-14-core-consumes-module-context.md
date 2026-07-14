# Minder Core Consumes Module Declarative Context — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Minder core consume a module's declarative context so the agent can *see* an SDK-integrated module — light static knowledge/notes in the prompt, richer tool descriptions, and an on-demand `read_module_context` tool for live state + on-screen snapshot.

**Architecture:** Capture the live-manifest `context` block onto the connector registry record at reconcile time. Fold each tool's `when_to_use`/`examples` into the proxy tool `description`. Render each module's `knowledge`/`notes` into its SKILL prompt block (offline, from the record). Add `RemoteConnector.fetch_context()` and a `read_module_context(module_name)` agent tool that returns live `state` + `ui_snapshot` (from `/connector/context`) merged with the record's static `knowledge`/`notes`.

**Tech Stack:** Python 3.13, httpx (mocked via `httpx.MockTransport` in tests), pytest. Core package `minder/core`.

## Global Constraints

- Consumer-side only (`minder/core`): core *reads* what the SDK already exposes; no new connector endpoints, no change to tool invocation/gating.
- Prompt build must stay **offline** — static `knowledge`/`notes` come from the connector *record* (captured at reconcile), never a fresh network call.
- Live `state`/`ui_snapshot` stay behind the `read_module_context` tool (dynamic).
- Inject `knowledge`/`notes` for **all** modules (no active-module scoping).
- Everything fail-soft: a missing/malformed manifest `context`, an offline module, or an unknown module name must never raise or block registration/prompt build.
- Line length 100, Google-style docstrings, mypy-strict on public APIs.
- Test command: `.venv/bin/pytest tests/<file> -q` from repo root.
- Commits: no `Co-Authored-By: Claude` trailer.

## Key existing symbols (verified)

- `minder/core/modules/registry.py`: `@dataclass ConnectorRecord(name, connector_url, remote_entry, api_base, state, tools: List[dict], fail_count, last_seen)`; `ModuleRegistry.register_connector(name=, connector_url=)`, `mark_connector_ready(name, tools)`, `connector(name) -> Optional[ConnectorRecord]`, `connector_records()`; `ConnectorState.{PENDING,READY,DOWN}`; module-level `get_registry() -> ModuleRegistry`.
- `minder/core/modules/watcher.py:206-207`: `tools = manifest.get("tools") or []` then `reg.mark_connector_ready(rec.name, tools)`.
- `minder/core/modules/remote.py`: `RemoteConnector(name, connector_url)`; `_auth_headers(name, principal, session_id=None, autonomy=None)`; `fetch_manifest()`; `build_remote_tool_specs(ctx, _modules)` builds `ToolSpec`s from `rec.tools`.
- `minder/core/skill_tools.py`: `@dataclass ToolSpec(name, description, parameters, handler, card_path=None)`; `SkillToolContext(... session_id, principal, logger ...)`.
- `minder/core/modules/prompt.py`: `render_module_section(m: Module) -> list[str]`; `build_skill_block(registry)`.
- Tests: `tests/test_connector_registry.py`, `tests/test_remote_connector.py` (use `httpx.MockTransport`).

---

### Task 1: Capture manifest `context` onto the connector record

**Files:**
- Modify: `minder/core/modules/registry.py` (`ConnectorRecord` ~lines 32-42; `mark_connector_ready` ~lines 181-192)
- Modify: `minder/core/modules/watcher.py` (~lines 206-207)
- Test: `tests/test_connector_registry.py` (append)

**Interfaces:**
- Produces: `ConnectorRecord.context: dict` (default `{}`); `mark_connector_ready(name, tools, context=None)` stores a normalized `context` dict; `connector(name).context` exposes it.

- [ ] **Step 1: Write the failing test (append to `tests/test_connector_registry.py`)**

```python
def test_mark_connector_ready_stores_context_block(tmp_path):
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready(
        "m",
        [{"name": "m_tool"}],
        context={"knowledge": ["K1"], "notes": [{"name": "a", "text": "t"}]},
    )
    rec = reg.connector("m")
    assert rec.context == {"knowledge": ["K1"], "notes": [{"name": "a", "text": "t"}]}


def test_mark_connector_ready_defaults_context_to_empty_dict(tmp_path):
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready("m", [{"name": "m_tool"}])  # no context arg
    assert reg.connector("m").context == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_connector_registry.py -q -k context`
Expected: FAIL — `TypeError: mark_connector_ready() got an unexpected keyword argument 'context'`

- [ ] **Step 3: Add the `context` field to `ConnectorRecord`**

In `minder/core/modules/registry.py`, add a field to the dataclass (after `tools`):

```python
    tools: List[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    fail_count: int = 0
```

- [ ] **Step 4: Accept + store `context` in `mark_connector_ready`**

Replace the body of `mark_connector_ready` (~lines 181-192) with:

```python
    def mark_connector_ready(
        self, name: str, tools: List[dict], context: Optional[dict] = None
    ) -> None:
        with self._lock:
            rec = self._connectors.get(name)
            if rec is None:
                return
            ctx_block = context if isinstance(context, dict) else {}
            changed = (
                rec.state != ConnectorState.READY
                or rec.tools != tools
                or rec.context != ctx_block
            )
            rec.state = ConnectorState.READY
            rec.tools = list(tools)
            rec.context = ctx_block
            rec.fail_count = 0
            rec.last_seen = time.time()
            if changed:
                self._version += 1
```

- [ ] **Step 5: Capture `context` in the watcher reconcile**

In `minder/core/modules/watcher.py`, replace lines ~206-207:

```python
            tools = manifest.get("tools") or []
            context = manifest.get("context") if isinstance(manifest.get("context"), dict) else {}
            reg.mark_connector_ready(rec.name, tools, context=context)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_connector_registry.py -q`
Expected: PASS (existing + 2 new)

- [ ] **Step 7: Commit**

```bash
git add minder/core/modules/registry.py minder/core/modules/watcher.py tests/test_connector_registry.py
git commit -m "feat(core): capture module manifest context onto connector record"
```

---

### Task 2: `RemoteConnector.fetch_context()`

**Files:**
- Modify: `minder/core/modules/remote.py` (add method after `fetch_manifest`, ~line 263)
- Test: `tests/test_remote_connector.py` (append)

**Interfaces:**
- Produces: `RemoteConnector.fetch_context(timeout=5.0, principal=None, session_id=None) -> Optional[dict]` — GET `/connector/context` with auth headers; parsed dict or `None` on error.

- [ ] **Step 1: Write the failing test (append to `tests/test_remote_connector.py`)**

```python
def test_fetch_context_returns_state_payload():
    def handler(request):
        assert request.url.path == "/connector/context"
        return httpx.Response(200, json={
            "state": [{"name": "inventory", "value": {"total": 2}}],
            "ui_snapshot": {"page": "products"},
            "actions": [],
        })
    conn = _connector(handler)
    out = conn.fetch_context()
    assert out["state"][0]["name"] == "inventory"
    assert out["ui_snapshot"]["page"] == "products"


def test_fetch_context_returns_none_on_error():
    def handler(request):
        return httpx.Response(503, json={"error": "down"})
    conn = _connector(handler)
    assert conn.fetch_context() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_remote_connector.py -q -k fetch_context`
Expected: FAIL — `AttributeError: 'RemoteConnector' object has no attribute 'fetch_context'`

- [ ] **Step 3: Add `fetch_context` (after `fetch_manifest`)**

```python
    def fetch_context(
        self, timeout: float = 5.0, principal: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Fetch the live ``/connector/context`` (autonomy, actions, live
        ``state`` and the current ``ui_snapshot``), or None if unreachable."""
        try:
            r = self._client.get(
                "/connector/context",
                headers=_auth_headers(self.name, principal, session_id),
                timeout=timeout,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else None
        except (httpx.HTTPError, ValueError):
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_remote_connector.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add minder/core/modules/remote.py tests/test_remote_connector.py
git commit -m "feat(core): add RemoteConnector.fetch_context()"
```

---

### Task 3: Fold `when_to_use` + `examples` into proxy tool descriptions

**Files:**
- Modify: `minder/core/modules/remote.py` (add `_enrich_description` helper; use it in `build_remote_tool_specs` ~lines 437-448)
- Test: `tests/test_module_context.py` (create)

**Interfaces:**
- Produces: `_enrich_description(tool: dict) -> str` — description with optional "When to use: …" and "Examples: …" appended.
- Consumes: `json` (already imported in `remote.py`).

- [ ] **Step 1: Write the failing test (create `tests/test_module_context.py`)**

```python
"""Unit tests for core consuming module declarative context."""
from __future__ import annotations

from minder.core.modules.remote import _enrich_description


def test_enrich_description_appends_when_to_use_and_examples():
    tool = {
        "name": "create_product",
        "description": "Create a product.",
        "when_to_use": "When the user provides SKU and price.",
        "examples": [{"sku": "A-1", "price": 9.9}],
    }
    out = _enrich_description(tool)
    assert "Create a product." in out
    assert "When to use: When the user provides SKU and price." in out
    assert '{"sku":"A-1","price":9.9}' in out


def test_enrich_description_plain_when_no_metadata():
    assert _enrich_description({"description": "Just a tool."}) == "Just a tool."
    assert _enrich_description({}) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_module_context.py -q -k enrich`
Expected: FAIL — `ImportError: cannot import name '_enrich_description'`

- [ ] **Step 3: Add `_enrich_description` (near `build_remote_tool_specs` in `remote.py`)**

```python
def _enrich_description(tool: dict) -> str:
    """Fold a tool's ``when_to_use`` + ``examples`` into the description the LLM
    sees, so the agent picks and understands the tool better."""
    desc = (tool.get("description") or "").strip()
    parts = [desc] if desc else []
    when = (tool.get("when_to_use") or "").strip()
    if when:
        parts.append(f"When to use: {when}")
    examples = tool.get("examples") or []
    if examples:
        try:
            rendered = "; ".join(json.dumps(e, separators=(",", ":")) for e in examples)
        except (TypeError, ValueError):
            rendered = ""
        if rendered:
            parts.append(f"Examples: {rendered}")
    return "\n\n".join(parts)
```

- [ ] **Step 4: Use it in `build_remote_tool_specs`**

In `build_remote_tool_specs`, change the `ToolSpec(...)` construction to use the enriched description:

```python
            specs.append(
                ToolSpec(
                    name=name,
                    description=_enrich_description(tool),
                    parameters=tool.get("parameters", {"type": "object", "properties": {}}),
                    handler=_make_handler(ctx, conn, name, bool(tool.get("streaming"))),
                )
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_module_context.py -q -k enrich`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add minder/core/modules/remote.py tests/test_module_context.py
git commit -m "feat(core): fold when_to_use/examples into proxy tool description"
```

---

### Task 4: `read_module_context` agent tool

**Files:**
- Modify: `minder/core/modules/remote.py` (add `build_module_context_spec`; append it in `build_remote_tool_specs`)
- Test: `tests/test_module_context.py` (append)

**Interfaces:**
- Consumes: `RemoteConnector.fetch_context` (Task 2); `ConnectorRecord.context` (Task 1); `get_registry`, `ConnectorState`, `ToolSpec`.
- Produces: `build_module_context_spec(ctx: SkillToolContext) -> ToolSpec` named `read_module_context`. Handler returns `{"success": bool, "output": {...}}` where output has `state`, `ui_snapshot`, `knowledge`, `notes`.

- [ ] **Step 1: Write the failing test (append to `tests/test_module_context.py`)**

```python
def test_read_module_context_merges_live_state_and_static(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="m", connector_url="http://m:9200")
    reg.mark_connector_ready(
        "m", [{"name": "m_tool"}],
        context={"knowledge": ["K1"], "notes": [{"name": "a", "text": "t"}]},
    )
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)
    monkeypatch.setattr(
        remote.RemoteConnector, "fetch_context",
        lambda self, **kw: {"state": [{"name": "inv", "value": {"n": 2}}],
                            "ui_snapshot": {"page": "products"}},
    )

    class _Ctx:
        principal = {"username": "alice"}
        session_id = "s1"

    spec = remote.build_module_context_spec(_Ctx())
    assert spec.name == "read_module_context"
    out = spec.handler(module_name="m")
    assert out["success"] is True
    assert out["output"]["state"][0]["name"] == "inv"
    assert out["output"]["ui_snapshot"]["page"] == "products"
    assert out["output"]["knowledge"] == ["K1"]
    assert out["output"]["notes"] == [{"name": "a", "text": "t"}]


def test_read_module_context_unknown_module_is_soft_error(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="nope")
    assert out["success"] is False and "not reachable" in out["output"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_module_context.py -q -k read_module_context`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_module_context_spec'`

- [ ] **Step 3: Add `build_module_context_spec` (near `build_remote_tool_specs` in `remote.py`)**

```python
def build_module_context_spec(ctx: "SkillToolContext") -> "ToolSpec":
    """A single agent tool that reads a module's LIVE state + on-screen snapshot
    (from /connector/context) merged with its static knowledge/notes (from the
    connector record). The agent calls this when asked what a module shows."""
    from minder.core.skill_tools import ToolSpec  # local import: avoid cycle

    def handler(**kwargs: Any) -> dict:
        name = str(kwargs.get("module_name") or "").strip()
        if not name:
            return {"success": False, "output": "module_name is required"}
        from minder.core.modules.registry import ConnectorState, get_registry

        rec = get_registry().connector(name)
        if rec is None or rec.state is not ConnectorState.READY:
            return {"success": False, "output": f"module {name!r} is not reachable"}
        conn = RemoteConnector(rec.name, rec.connector_url)
        data = conn.fetch_context(principal=ctx.principal, session_id=ctx.session_id)
        if data is None:
            return {"success": False, "output": f"module {name!r} is not reachable"}
        static = rec.context or {}
        return {
            "success": True,
            "output": {
                "state": data.get("state", []),
                "ui_snapshot": data.get("ui_snapshot"),
                "knowledge": static.get("knowledge", []),
                "notes": static.get("notes", []),
            },
        }

    return ToolSpec(
        name="read_module_context",
        description=(
            "Read a module's live state, current on-screen snapshot, domain "
            "knowledge, and area notes. Call this when the user asks what a module "
            "currently shows or contains."
        ),
        parameters={
            "type": "object",
            "properties": {
                "module_name": {
                    "type": "string",
                    "description": "The module to inspect, e.g. 'module_template'.",
                }
            },
            "required": ["module_name"],
        },
        handler=handler,
    )
```

- [ ] **Step 4: Append the tool in `build_remote_tool_specs`**

Just before `return specs` in `build_remote_tool_specs`, add:

```python
    specs.append(build_module_context_spec(ctx))
    return specs
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_module_context.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add minder/core/modules/remote.py tests/test_module_context.py
git commit -m "feat(core): add read_module_context agent tool"
```

---

### Task 5: Inject `knowledge` + `notes` into the module SKILL block

**Files:**
- Modify: `minder/core/modules/prompt.py` (add `_render_context_block`; call it in `render_module_section` ~lines 77-94)
- Test: `tests/test_module_context.py` (append)

**Interfaces:**
- Produces: `_render_context_block(name: str, ctx: dict) -> list[str]` — prompt lines for knowledge/notes + the tool hint; `[]` when both empty.
- Consumes: `get_registry` (from `minder.core.modules.registry`) inside `render_module_section`.

- [ ] **Step 1: Write the failing test (append to `tests/test_module_context.py`)**

```python
def test_render_context_block_lists_knowledge_notes_and_hint():
    from minder.core.modules.prompt import _render_context_block

    lines = _render_context_block(
        "module_template",
        {"knowledge": ["Always confirm SKU."], "notes": [{"name": "products", "text": "Catalog."}]},
    )
    text = "\n".join(lines)
    assert "**Domain knowledge:**" in text
    assert "- Always confirm SKU." in text
    assert "- products: Catalog." in text
    assert "read_module_context('module_template')" in text


def test_render_context_block_empty_when_no_context():
    from minder.core.modules.prompt import _render_context_block

    assert _render_context_block("m", {}) == []
    assert _render_context_block("m", {"knowledge": [], "notes": []}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_module_context.py -q -k render_context_block`
Expected: FAIL — `ImportError: cannot import name '_render_context_block'`

- [ ] **Step 3: Add `_render_context_block` (above `render_module_section` in `prompt.py`)**

```python
def _render_context_block(name: str, ctx: dict) -> list[str]:
    """Prompt lines for a module's declarative context: static domain knowledge +
    area notes, and a hint to fetch live state via the read_module_context tool.
    Empty when the module declares no context."""
    knowledge = ctx.get("knowledge") or []
    notes = ctx.get("notes") or []
    if not knowledge and not notes:
        return []
    out: list[str] = []
    if knowledge:
        out += ["", "**Domain knowledge:**"]
        out += [f"- {k}" for k in knowledge]
    if notes:
        out += ["", "**Areas:**"]
        out += [f"- {n.get('name')}: {n.get('text')}" for n in notes if n.get("name")]
    out += [
        "",
        f"Call `read_module_context('{name}')` for live state and the current "
        "on-screen snapshot.",
    ]
    return out
```

- [ ] **Step 4: Call it from `render_module_section`**

In `render_module_section`, after the sub-skills block and before the files listing, add the record lookup + render:

```python
    if m.subskills:
        section += ["", "**Sub-skills**:"]
        for s in m.subskills:
            section.append(f'- `{m.name}:{s.name}` — {s.description}')

    from minder.core.modules.registry import get_registry

    rec = get_registry().connector(m.name)
    section += _render_context_block(m.name, (rec.context if rec else None) or {})

    listing = _format_files(list(m.files))
    if listing:
        section += ["", listing]
    return section
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_module_context.py -q`
Expected: PASS

- [ ] **Step 6: Run the full new-feature + touched suites (no regressions)**

Run: `.venv/bin/pytest tests/test_module_context.py tests/test_connector_registry.py tests/test_remote_connector.py -q`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add minder/core/modules/prompt.py tests/test_module_context.py
git commit -m "feat(core): render module knowledge/notes + tool hint in SKILL block"
```

---

### Task 6: End-to-end (real, docker already running)

**Files:** none (verification only).

- [ ] **Step 1: Rebuild + restart the minder container so it runs the new core**

Run:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build minder
```
Expected: `minder` container recreated, healthy; `module-template-web`/`worker` still up.

- [ ] **Step 2: Confirm the agent can SEE the module (real turn)**

With `OPENAI_API_KEY` set in the environment the container uses, ask the module chat agent about `module_template`'s current state. Using the module chat route:

```bash
curl -s -X POST 'http://localhost:8000/api/modules/module_template/chat' \
  -H 'Content-Type: application/json' \
  -d '{"message": "Module module_template đang có gì trong kho ngay bây giờ?"}' | python -m json.tool
```
(Adjust host/port to how the web app is published — check `docker compose ... ps` / compose ports for the `minder` service.)

Expected: the agent's turn includes a `read_module_context` tool call whose result carries the live `state` (inventory total, jobs) and the products/jobs notes, and the final answer states the current inventory (e.g. reflects the "Giường" product created earlier). This proves core now consumes the module context end-to-end.

- [ ] **Step 3: (Optional) Confirm the enriched tool + prompt statically**

Run: `.venv/bin/pytest tests/test_module_context.py -q` one more time and eyeball that the module chat's system prompt (or a debug dump if available) contains a `**Domain knowledge:**` line for `module_template`.

- [ ] **Step 4: No commit** (verification task only).

---

## Self-Review

**Spec coverage:**
- A. `RemoteConnector.fetch_context()` → Task 2. ✓
- B. `read_module_context` tool (state + ui_snapshot + knowledge + notes, soft errors) → Task 4. ✓
- C. Fold `when_to_use`/`examples` into tool description → Task 3. ✓
- D. Inject knowledge/notes (all modules, static) + tool hint into SKILL block → Task 5. ✓
- Support: capture manifest `context` onto the connector record at reconcile → Task 1. ✓
- Offline prompt build (record, not network) → Task 5 reads `rec.context`; Task 1 populates it at reconcile. ✓
- Fail-soft everywhere → Task 1 normalizes malformed context; Task 2 returns None on error; Task 4 soft errors for unknown/offline; Task 5 empty when no context. ✓
- E2E → Task 6. ✓

**Placeholder scan:** No TBD/TODO. Every code step shows real code; every test shows real assertions. Task 6 Step 2 notes "adjust host/port" against a concrete command — an environment detail to confirm, not a code gap.

**Type consistency:** `mark_connector_ready(name, tools, context=None)` and `ConnectorRecord.context: dict` defined in Task 1 and consumed by the same names in Tasks 4 (`rec.context`) and 5 (`rec.context`). `RemoteConnector.fetch_context(..., principal, session_id)` defined in Task 2, called with those kwargs in Task 4. `_enrich_description(tool)` (Task 3), `build_module_context_spec(ctx) -> ToolSpec` named `read_module_context` (Task 4), and `_render_context_block(name, ctx)` (Task 5) are each defined and referenced by identical names. Output dict keys (`state`, `ui_snapshot`, `knowledge`, `notes`) match between Task 4's handler and its test.
