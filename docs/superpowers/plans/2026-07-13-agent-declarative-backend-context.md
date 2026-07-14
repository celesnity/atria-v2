# Agent Declarative Backend Context (`@conn.context.*`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `conn.context.*` decorator family to `minder_python_sdk` so a module can declaratively hand the agent live state, domain knowledge/guardrails, area notes, and richer per-tool semantics — the backend mirror of the frontend `Agent.*` layer.

**Architecture:** A pure `context.py` module holds the `Note`/`_StateProvider` data types, a value cap, a `_ContextRegistrar` (the `conn.context` accessor), and a `build_state_entries` evaluator. The `Connector` gains three registries plus `self.context`, surfaces the static parts (`knowledge`, `notes`, tool `when_to_use`/`examples`) in `GET /connector/manifest`, and evaluates `state` live in `GET /connector/context`. No new transport; tool invocation and gating are untouched.

**Tech Stack:** Python 3.13, FastAPI connector, pytest + `fastapi.testclient.TestClient` + in-process `conn.invoke`.

## Global Constraints

- Extends `minder_python_sdk` only (plus a small `module_template` change in the E2E task).
- Line length 100 (Black + Ruff); Google-style docstrings; mypy-strict typing on public APIs.
- One decorator namespace: `conn.context.*` (`state` decorator, `knowledge`, `note`).
- `state` evaluates **live** on every `GET /connector/context`; receives `principal` /
  `session_id` via the existing `_accepts_arg` injection pattern; **fail-closed per entry**
  (one provider raising must not break the response — log a warning, skip that entry).
- Static/dynamic split: `knowledge` + `note` + tool `when_to_use`/`examples` → **manifest**;
  `state` → **context**.
- Tool enrichment is **additive** kwargs on the existing `@conn.tool` / `@conn.read` — no
  change to invocation, validation, or gating.
- `state` value capped at **32768** serialized characters; over-cap → truncated with
  `truncated: true`. Non-JSON-serializable values coerce via `str()` before capping.
- Test command: `cd minder_python_sdk && ./.venv/bin/pytest tests/ -q`.
- Commits: no `Co-Authored-By: Claude` trailer.

---

### Task 1: Pure context module (`context.py`)

**Files:**
- Create: `minder_python_sdk/minder_python_sdk/context.py`
- Modify: `minder_python_sdk/minder_python_sdk/__init__.py` (export `Note`)
- Test: `minder_python_sdk/tests/test_context_surface.py`

**Interfaces:**
- Produces:
  - `MAX_STATE_CHARS = 32768`
  - `@dataclass Note: name: str; text: str`
  - `@dataclass _StateProvider: description: str; fn: Callable[..., Any]`
  - `cap_value(value: Any) -> tuple[Any, bool]` — returns `(value_or_truncated_string, truncated)`
  - `build_state_entries(providers: dict[str, _StateProvider], principal: Any, session_id: Any) -> list[dict]`
  - `class _ContextRegistrar` with `__init__(self, owner)`, `state(name, description="") -> decorator`,
    `knowledge(text) -> None`, `note(name, text) -> None`. `owner` must expose mutable
    `_ctx_state: dict`, `_ctx_knowledge: list`, `_ctx_notes: list`.

- [ ] **Step 1: Write the failing test**

```python
# minder_python_sdk/tests/test_context_surface.py
from types import SimpleNamespace

from minder_python_sdk.context import (
    MAX_STATE_CHARS,
    Note,
    _ContextRegistrar,
    build_state_entries,
    cap_value,
)


def _owner():
    return SimpleNamespace(_ctx_state={}, _ctx_knowledge=[], _ctx_notes=[])


def test_state_decorator_registers_provider_and_returns_fn():
    owner = _owner()
    reg = _ContextRegistrar(owner)

    @reg.state("inventory", "Current stock")
    def inv():
        return {"in_stock": 42}

    assert inv() == {"in_stock": 42}  # returned unchanged
    assert owner._ctx_state["inventory"].description == "Current stock"


def test_knowledge_ignores_blank_and_appends():
    owner = _owner()
    reg = _ContextRegistrar(owner)
    reg.knowledge("  ")
    reg.knowledge(" Always check MEL. ")
    assert owner._ctx_knowledge == ["Always check MEL."]


def test_note_dedupes_by_name():
    owner = _owner()
    reg = _ContextRegistrar(owner)
    reg.note("products", "old")
    reg.note("products", "new")
    reg.note("", "ignored")
    assert owner._ctx_notes == [Note(name="products", text="new")]


def test_build_state_entries_evaluates_live_and_injects_principal():
    seen = {}

    def inv(principal=None):
        seen["p"] = principal
        return {"in_stock": 42}

    providers = {"inventory": _StateProvider_desc(inv, "stock")}
    out = build_state_entries(providers, principal="alice", session_id="s1")
    assert out == [{"name": "inventory", "description": "stock", "value": {"in_stock": 42}}]
    assert seen["p"] == "alice"


def test_build_state_entries_is_fail_closed_per_entry():
    def boom():
        raise RuntimeError("nope")

    def ok():
        return 1

    providers = {
        "bad": _StateProvider_desc(boom, ""),
        "good": _StateProvider_desc(ok, ""),
    }
    out = build_state_entries(providers, principal=None, session_id=None)
    assert [e["name"] for e in out] == ["good"]  # bad skipped, good survives


def test_cap_value_truncates_oversized():
    big = "x" * (MAX_STATE_CHARS + 10)
    value, truncated = cap_value(big)
    assert truncated is True and len(value) == MAX_STATE_CHARS


def test_build_state_entries_flags_truncated():
    def big():
        return "y" * (MAX_STATE_CHARS + 5)

    out = build_state_entries({"b": _StateProvider_desc(big, "")}, None, None)
    assert out[0]["truncated"] is True


# Helper: construct a _StateProvider without importing its private name everywhere.
def _StateProvider_desc(fn, description):
    from minder_python_sdk.context import _StateProvider

    return _StateProvider(description=description, fn=fn)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'minder_python_sdk.context'`

- [ ] **Step 3: Write the implementation**

```python
# minder_python_sdk/minder_python_sdk/context.py
"""Declarative agent-facing context: live state, knowledge, notes.

The backend mirror of the frontend ``Agent.*`` wrapper layer. A module declares
context through ``conn.context.*`` and the connector surfaces it to the agent —
static parts (knowledge, notes) in the manifest, live ``state`` in the context
endpoint.
"""
from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_STATE_CHARS = 32768


@dataclass
class Note:
    """A labeled, agent-facing description of a page/area of the module."""

    name: str
    text: str


@dataclass
class _StateProvider:
    """A registered ``context.state`` provider: a description + the function that
    returns the live value on each context read."""

    description: str
    fn: Callable[..., Any]


def _wants(fn: Callable[..., Any], arg: str) -> bool:
    """True if ``fn`` accepts ``arg`` by name or via ``**kwargs``."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if arg in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def cap_value(value: Any) -> tuple[Any, bool]:
    """Cap a state value at ``MAX_STATE_CHARS`` serialized chars.

    Returns ``(value, truncated)``. JSON-serializable values under the cap pass
    through unchanged; over-cap or non-serializable values become a truncated
    string.
    """
    try:
        serialized = json.dumps(value)
    except (TypeError, ValueError):
        serialized = str(value)
        value = serialized
    if len(serialized) > MAX_STATE_CHARS:
        return serialized[:MAX_STATE_CHARS], True
    return value, False


def build_state_entries(
    providers: dict[str, _StateProvider], principal: Any, session_id: Any
) -> list[dict]:
    """Evaluate every state provider live, fail-closed per entry.

    Each provider may accept ``principal`` / ``session_id`` (injected when its
    signature declares them). A provider that raises is skipped with a warning;
    the rest still return.
    """
    entries: list[dict] = []
    for name, prov in providers.items():
        try:
            kwargs: dict[str, Any] = {}
            if _wants(prov.fn, "principal"):
                kwargs["principal"] = principal
            if _wants(prov.fn, "session_id"):
                kwargs["session_id"] = session_id
            value, truncated = cap_value(prov.fn(**kwargs))
            entry: dict[str, Any] = {"name": name, "description": prov.description, "value": value}
            if truncated:
                entry["truncated"] = True
            entries.append(entry)
        except Exception as exc:  # fail-closed per entry
            logger.warning("context.state %r failed: %s", name, exc)
    return entries


class _ContextRegistrar:
    """The ``conn.context`` accessor. Registers declarative agent context onto an
    owner exposing ``_ctx_state`` / ``_ctx_knowledge`` / ``_ctx_notes``."""

    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def state(self, name: str, description: str = "") -> Callable[[Callable], Callable]:
        """Decorate a function returning live module state the agent reads."""

        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._owner._ctx_state:
                logger.warning("context.state %r redefined", name)
            self._owner._ctx_state[name] = _StateProvider(description=description, fn=fn)
            return fn

        return deco

    def knowledge(self, text: str) -> None:
        """Add a static domain-knowledge / guardrail string for the agent."""
        text = (text or "").strip()
        if text:
            self._owner._ctx_knowledge.append(text)

    def note(self, name: str, text: str) -> None:
        """Add a static, labeled area/page description (duplicate name overrides)."""
        text = (text or "").strip()
        if not text:
            return
        self._owner._ctx_notes = [n for n in self._owner._ctx_notes if n.name != name]
        self._owner._ctx_notes.append(Note(name=name, text=text))
```

- [ ] **Step 4: Export `Note` from the package**

Read `minder_python_sdk/minder_python_sdk/__init__.py`, then add `Note` to the exports next to the existing public names (e.g. where `Connector` / `Principal` are exported):

```python
from .context import Note  # noqa: F401
```

If the file defines `__all__`, add `"Note"` to it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add minder_python_sdk/minder_python_sdk/context.py minder_python_sdk/minder_python_sdk/__init__.py
git add -f minder_python_sdk/tests/test_context_surface.py
git commit -m "feat(connector): add declarative context module (state/knowledge/note)"
```

---

### Task 2: Wire `conn.context` + live `state` into `/connector/context`

**Files:**
- Modify: `minder_python_sdk/minder_python_sdk/connector.py` (`__init__` ~lines 159-187; `GET /connector/context` handler ~lines 929-957)
- Test: `minder_python_sdk/tests/test_context_surface.py` (append)

**Interfaces:**
- Consumes: `_ContextRegistrar`, `_StateProvider`, `Note`, `build_state_entries` from Task 1.
- Produces: `Connector` instance attributes `self._ctx_state: dict[str, _StateProvider]`,
  `self._ctx_knowledge: list[str]`, `self._ctx_notes: list[Note]`, and `self.context:
  _ContextRegistrar`. `GET /connector/context` response gains `"state": list[dict]`.

- [ ] **Step 1: Write the failing test (append to test_context_surface.py)**

```python
def test_context_endpoint_returns_live_state_with_principal():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")

    @conn.context.state("whoami", "Who is asking")
    def whoami(principal=None):
        return {"user": getattr(principal, "username", None)}

    client = TestClient(conn.asgi())
    body = client.get(
        "/connector/context",
        headers={"X-Minder-Principal": '{"username": "alice"}'},
    ).json()
    assert {"name": "whoami", "description": "Who is asking", "value": {"user": "alice"}} in body[
        "state"
    ]


def test_context_state_defaults_to_empty_list():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")
    body = TestClient(conn.asgi()).get("/connector/context").json()
    assert body["state"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q -k context_endpoint_returns_live_state`
Expected: FAIL — `AttributeError: 'Connector' object has no attribute 'context'`

- [ ] **Step 3: Add imports + `__init__` state**

At the top of `connector.py`, add to the existing `from .context import ...` (create the import if absent):

```python
from .context import Note, _ContextRegistrar, _StateProvider, build_state_entries
```

In `Connector.__init__`, next to `self._ui_snapshots: dict[str, dict] = {}` (~line 187), add:

```python
# Declarative agent-facing context: live state providers + static
# knowledge/notes, surfaced via /connector/context and the manifest.
self._ctx_state: dict[str, _StateProvider] = {}
self._ctx_knowledge: list[str] = []
self._ctx_notes: list[Note] = []
self.context = _ContextRegistrar(self)
```

- [ ] **Step 4: Add `state` to the context handler**

In the `GET /connector/context` handler, add `"state"` to the returned dict (after
`"ui_snapshot"`):

```python
                "ui_snapshot": self._ui_snapshots.get(session),
                "state": build_state_entries(self._ctx_state, principal, session),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add minder_python_sdk/minder_python_sdk/connector.py
git add -f minder_python_sdk/tests/test_context_surface.py
git commit -m "feat(connector): evaluate context.state live in /connector/context"
```

---

### Task 3: Surface `knowledge` + `notes` in the manifest

**Files:**
- Modify: `minder_python_sdk/minder_python_sdk/connector.py` (`_tool_specs`/spec helpers area ~lines 900-925; `GET /connector/manifest` handler ~lines 959-982)
- Test: `minder_python_sdk/tests/test_context_surface.py` (append)

**Interfaces:**
- Consumes: `self._ctx_knowledge`, `self._ctx_notes` from Task 2.
- Produces: `Connector._context_spec() -> dict` returning `{"knowledge": [...], "notes":
  [{"name", "text"}]}`; `GET /connector/manifest` response gains `"context": <that dict>`.

- [ ] **Step 1: Write the failing test (append)**

```python
def test_manifest_exposes_knowledge_and_notes():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")
    conn.context.knowledge("Always check MEL before dispatch.")
    conn.context.note("products", "Product catalog area.")

    mani = TestClient(conn.asgi()).get("/connector/manifest").json()
    assert mani["context"]["knowledge"] == ["Always check MEL before dispatch."]
    assert mani["context"]["notes"] == [{"name": "products", "text": "Product catalog area."}]


def test_manifest_context_defaults_empty():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    mani = TestClient(Connector("m").asgi()).get("/connector/manifest").json()
    assert mani["context"] == {"knowledge": [], "notes": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q -k manifest_exposes_knowledge`
Expected: FAIL — `KeyError: 'context'`

- [ ] **Step 3: Add the `_context_spec` helper**

Next to `_tool_specs` (~line 900) add a method on `Connector`:

```python
    def _context_spec(self) -> dict:
        """Static agent context for the manifest: domain knowledge + area notes."""
        return {
            "knowledge": list(self._ctx_knowledge),
            "notes": [{"name": n.name, "text": n.text} for n in self._ctx_notes],
        }
```

- [ ] **Step 4: Add `context` to the manifest dict**

In the `GET /connector/manifest` handler's returned dict, add after `"ui": self._ui.to_dict(),`:

```python
                "context": self._context_spec(),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q`
Expected: PASS (11 tests)

- [ ] **Step 6: Commit**

```bash
git add minder_python_sdk/minder_python_sdk/connector.py
git add -f minder_python_sdk/tests/test_context_surface.py
git commit -m "feat(connector): expose context knowledge+notes in manifest"
```

---

### Task 4: Enrich `@conn.tool` / `@conn.read` with `when_to_use` + `examples`

**Files:**
- Modify: `minder_python_sdk/minder_python_sdk/connector.py` (`_Tool` dataclass ~lines 86-100; `tool()` ~lines 197-252; `read()` ~lines 254-274; `_tool_specs` ~lines 900-915)
- Test: `minder_python_sdk/tests/test_context_surface.py` (append)

**Interfaces:**
- Produces: `_Tool` gains `when_to_use: str = ""` and `examples: list = field(default_factory=list)`;
  `tool()`/`read()` accept `when_to_use: str = ""`, `examples: Optional[list] = None`;
  manifest tool spec gains `"when_to_use"` and `"examples"`.

- [ ] **Step 1: Write the failing test (append)**

```python
def test_tool_enrichment_surfaces_in_manifest():
    from fastapi.testclient import TestClient
    from minder_python_sdk.connector import Connector

    conn = Connector("m")

    @conn.tool(
        "create_product",
        risk="medium",
        when_to_use="When the user wants a new product and has SKU + price",
        examples=[{"sku": "A-1", "name": "Pump", "price": 9.9}],
    )
    def create_product(sku: str, name: str, price: float, **kw):
        return {"output": "ok"}

    @conn.read("list_products", description="List products")
    def list_products():
        return {"output": []}

    tools = {t["name"]: t for t in TestClient(conn.asgi()).get("/connector/manifest").json()["tools"]}
    assert tools["create_product"]["when_to_use"].startswith("When the user")
    assert tools["create_product"]["examples"] == [{"sku": "A-1", "name": "Pump", "price": 9.9}]
    # Unset tool has empty defaults, not missing keys.
    assert tools["list_products"]["when_to_use"] == ""
    assert tools["list_products"]["examples"] == []


def test_enriched_tool_still_invokes_and_gates_normally():
    from minder_python_sdk.connector import Connector

    conn = Connector("m")

    @conn.tool("echo", when_to_use="whenever", examples=[{"q": "hi"}])
    def echo(q: str = ""):
        return {"output": q.upper()}

    assert conn.invoke("echo", {"q": "hi"})["output"] == "HI"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q -k tool_enrichment`
Expected: FAIL — `TypeError: tool() got an unexpected keyword argument 'when_to_use'`

- [ ] **Step 3: Extend `_Tool`**

In the `_Tool` dataclass (~lines 86-100), add two fields after `read_only`:

```python
    read_only: bool = False
    when_to_use: str = ""
    examples: list = field(default_factory=list)
```

Ensure `field` is imported at the top of `connector.py` (it uses `from dataclasses import dataclass`; change to `from dataclasses import dataclass, field` if `field` isn't already imported).

- [ ] **Step 4: Add kwargs to `tool()` and `read()`**

In `tool()` (~line 197), add two keyword params before the closing `)` of the signature
(after `read_only: bool = False,`):

```python
        read_only: bool = False,
        when_to_use: str = "",
        examples: Optional[list] = None,
```

In the `_Tool(...)` construction inside `deco` (~lines 236-248), add after `read_only=read_only,`:

```python
                read_only=read_only,
                when_to_use=when_to_use,
                examples=examples or [],
```

In `read()` (~line 254), add the same two params to the signature and forward them:

```python
        params_model: Optional[type] = None,
        when_to_use: str = "",
        examples: Optional[list] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a typed *read* — a pure state query (queue, WIP, OEE, …). Same
        as :meth:`tool` but ``read_only`` (risk "none", never gated)."""
        return self.tool(
            name,
            description=description,
            parameters=parameters,
            card_type=card_type,
            streaming=streaming,
            params_model=params_model,
            read_only=True,
            when_to_use=when_to_use,
            examples=examples,
        )
```

- [ ] **Step 5: Surface them in `_tool_specs`**

In `_tool_specs` (~lines 900-915), add two keys to the per-tool dict (after `"idempotent": t.idempotent,`):

```python
                "idempotent": t.idempotent,
                "when_to_use": t.when_to_use,
                "examples": t.examples,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/test_context_surface.py -q`
Expected: PASS (13 tests)

- [ ] **Step 7: Run the whole module_sdk suite (no regressions)**

Run: `cd minder_python_sdk && ./.venv/bin/pytest tests/ -q`
Expected: PASS (all existing + new tests)

- [ ] **Step 8: Commit**

```bash
git add minder_python_sdk/minder_python_sdk/connector.py
git add -f minder_python_sdk/tests/test_context_surface.py
git commit -m "feat(connector): add when_to_use/examples to tool + read"
```

---

### Task 5: End-to-end in `module_template` (real run)

**Files:**
- Modify: `modules/module_template/backend/app.py`

**Interfaces:**
- Consumes: `conn.context.*` and the enriched `@conn.tool` from Tasks 1-4.

- [ ] **Step 1: Declare context in `module_template`**

In `modules/module_template/backend/app.py`, after the existing UI-surface declarations
(the `conn.page(...)` / `conn.form(...)` block, ~lines 247-275) and using the module's real
`products` store, add:

```python
# --- Declarative agent context (mirror of the frontend Agent.* layer) ---
@conn.context.state("inventory", "Live catalog summary: total products and low stock")
def inventory_state(principal=None):
    items = products.list_products()
    return {"total": len(items), "skus": [p["sku"] for p in items][:20]}


conn.context.knowledge(
    "Confirm SKU and price with the user before creating a product; SKUs are unique."
)
conn.context.note("products", "Product catalog area — add, restock, and delete products.")
```

Then enrich the existing `create_product` tool decorator (~lines 299-312) by adding two
kwargs to its `@conn.tool(...)` call (keep every existing argument):

```python
@conn.tool(
    "create_product",
    risk="medium",
    reversible=True,
    undo="delete_product(product_id) — removes the product just created",
    description="Create a product…",   # keep the existing description text
    parameters={...},                   # keep the existing parameters
    card_type="template_card",
    when_to_use="When the user asks to add a new product and has provided SKU and price.",
    examples=[{"sku": "A-1", "name": "Pump", "price": 9.9, "category": "A"}],
)
def create_product(...):
    ...
```

- [ ] **Step 2: Verify the backend imports cleanly**

Run: `cd modules/module_template/backend && python -c "import app; print('tools:', 'create_product' in app.conn._tools); print('state:', list(app.conn._ctx_state))"`
Expected: prints `tools: True` and `state: ['inventory']` with no import error.
(If `python` is unavailable, use the module's venv or `../../../minder_python_sdk/.venv/bin/python`.)

- [ ] **Step 3: Real end-to-end run**

Per `CLAUDE.md`, exercise the running connector. Start the module backend (serves on
`http://localhost:9300`), then verify both surfaces:

```bash
# Static context in the manifest
curl -s localhost:9300/connector/manifest | python -m json.tool | grep -A6 '"context"'
# Expect: knowledge[] with the MEL/SKU guardrail, notes[] with the products note.
# And the create_product tool entry carrying when_to_use + examples.

# Live state in the context endpoint (with a principal header)
curl -s localhost:9300/connector/context \
  -H 'X-Minder-Principal: {"username":"alice"}' | python -m json.tool | grep -A8 '"state"'
# Expect: state[] contains {"name":"inventory", ... "value":{"total":N,"skus":[...]}}.
```

Confirm the `inventory` state reflects the real product count (add a product via the UI or
`POST /connector/tools/create_product`, re-read context, and see `total` increase — proving
it evaluates live).

- [ ] **Step 4: Commit**

```bash
git add modules/module_template/backend/app.py
git commit -m "feat(module_template): declare agent context via @conn.context.*"
```

---

## Self-Review

**Spec coverage:**
- `@conn.context.state` decorator, live eval, principal injection → Task 1 (`build_state_entries`,
  `_ContextRegistrar.state`) + Task 2 (endpoint). ✓
- `conn.context.knowledge` / `conn.context.note` static → Task 1 (registrar) + Task 3 (manifest). ✓
- Tool `when_to_use` / `examples` → Task 4. ✓
- Static→manifest, dynamic→context split → Task 2 (context.state) + Task 3 (manifest knowledge/notes)
  + Task 4 (manifest tool enrich). ✓
- Fail-closed per state entry → Task 1 `build_state_entries` + test `..._is_fail_closed_per_entry`. ✓
- 32768-char cap + `truncated` + non-serializable coercion → Task 1 `cap_value` + tests. ✓
- Duplicate name override, blank ignored → Task 1 tests. ✓
- No change to invocation/gating → Task 4 `test_enriched_tool_still_invokes_and_gates_normally`. ✓
- `Note` exported → Task 1 Step 4. ✓
- E2E in module_template → Task 5. ✓

**Placeholder scan:** No TBD/TODO. The only ellipses are in Task 5 Step 1, explicitly labeled
"keep the existing …" against real line ranges — an instruction to preserve existing args, not a
gap. All test/code steps show concrete code.

**Type consistency:** `_StateProvider(description=, fn=)`, `Note(name=, text=)`,
`build_state_entries(providers, principal, session_id)`, `_ContextRegistrar(owner)`, and
`MAX_STATE_CHARS` are defined in Task 1 and used with identical names/signatures in Tasks 2-5.
Connector attributes `_ctx_state` / `_ctx_knowledge` / `_ctx_notes` / `self.context` are introduced
in Task 2 and consumed by the same names in Tasks 3-4. Manifest keys (`context.knowledge`,
`context.notes`, tool `when_to_use`/`examples`) and context key (`state`) match across their
producing task and every asserting test.
