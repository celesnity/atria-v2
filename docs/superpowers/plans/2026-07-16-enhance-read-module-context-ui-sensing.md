# Enhance `read_module_context` UI Sensing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the agent's existing `read_module_context` tool return a compact, LLM-shaped view of a module's live UI (page / data / buttons / actions) and teach the agent which modules it can inspect when it names the wrong one.

**Architecture:** Add a pure `shape_ui_context()` helper that flattens the `/connector/context` envelope, then wire it plus a discovery-on-miss listing into the existing `build_module_context_spec` handler in `remote.py`. No new tool, no registry or schema changes — the tool is a dynamically built `ToolSpec`.

**Tech Stack:** Python 3.13, pytest, `uv run` for env management.

## Global Constraints

- Line length: 100 chars (Black + Ruff). Run `uv run black` / `uv run ruff` before commit.
- Type hints on public APIs (mypy strict). Google-style docstrings.
- Tests run via `uv run pytest`.
- No changes to `minder_ui_sdk` or `minder_python_sdk` — the snapshot contract already exists.
- `read_module_context` must not regress: `state`, `knowledge`, `notes` stay in the output.

---

### Task 1: Pure `shape_ui_context()` helper

**Files:**
- Create: `minder/core/modules/ui_context.py`
- Test: `tests/test_ui_context_shaper.py`

**Interfaces:**
- Consumes: nothing (pure function over a dict).
- Produces: `shape_ui_context(raw: dict) -> dict` returning keys
  `page: str | None`, `data: list[dict]`, `buttons: list[dict]`,
  `actions: list[dict]`, `autonomy: str | None`, `principal: dict | None`.
  Input `raw` is the `fetch_context()` envelope:
  `{module, autonomy, principal:{username,authenticated,roles,scopes},
    actions:[{name,risk,read_only,reversible,undo,allowed}],
    ui_snapshot:{page,data:[{name,description,value,truncated}],actions:[{name,description}]} | None,
    state:[...]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ui_context_shaper.py
"""Unit tests for the pure UI-context shaper."""
from __future__ import annotations

from minder.core.modules.ui_context import shape_ui_context

FULL = {
    "module": "produce",
    "autonomy": "low",
    "principal": {"username": "alice", "authenticated": True,
                  "roles": ["op"], "scopes": ["read"]},
    "actions": [
        {"name": "cmd_start", "risk": "medium", "read_only": False,
         "reversible": True, "undo": None, "allowed": False},
    ],
    "ui_snapshot": {
        "page": "operator",
        "data": [{"name": "wip", "description": "WIP count", "value": 12,
                  "truncated": False}],
        "actions": [{"name": "startJob", "description": "Start the job"}],
    },
    "state": [{"name": "inv", "value": {"n": 2}}],
}


def test_shape_full_envelope():
    out = shape_ui_context(FULL)
    assert out["page"] == "operator"
    assert out["data"] == [{"name": "wip", "description": "WIP count",
                            "value": 12, "truncated": False}]
    assert out["buttons"] == [{"name": "startJob", "description": "Start the job"}]
    assert out["actions"] == [{"name": "cmd_start", "risk": "medium",
                               "read_only": False, "allowed": False}]
    assert out["autonomy"] == "low"
    assert out["principal"]["username"] == "alice"


def test_shape_missing_ui_snapshot():
    out = shape_ui_context({"autonomy": "high", "actions": [], "ui_snapshot": None})
    assert out["page"] is None
    assert out["data"] == []
    assert out["buttons"] == []
    assert out["actions"] == []
    assert out["principal"] is None


def test_shape_empty_envelope():
    out = shape_ui_context({})
    assert out == {"page": None, "data": [], "buttons": [],
                   "actions": [], "autonomy": None, "principal": None}


def test_shape_preserves_truncated_and_trims_action_fields():
    raw = {
        "actions": [{"name": "a", "risk": "low", "read_only": True,
                     "reversible": True, "undo": "x", "allowed": True}],
        "ui_snapshot": {"page": None,
                        "data": [{"name": "big", "value": "x", "truncated": True}],
                        "actions": []},
    }
    out = shape_ui_context(raw)
    assert out["data"][0]["truncated"] is True
    # trimmed: reversible/undo dropped from the action view
    assert out["actions"][0] == {"name": "a", "risk": "low",
                                 "read_only": True, "allowed": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ui_context_shaper.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'minder.core.modules.ui_context'`

- [ ] **Step 3: Write the implementation**

```python
# minder/core/modules/ui_context.py
"""Shape a module connector's ``/connector/context`` envelope into a compact,
LLM-friendly view of the live UI (page, on-screen data, buttons, tool actions)."""

from __future__ import annotations

from typing import Any


def _shape_data(entry: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": entry.get("name"),
        "description": entry.get("description"),
        "value": entry.get("value"),
    }
    if entry.get("truncated"):
        out["truncated"] = True
    return out


def _shape_button(entry: dict[str, Any]) -> dict[str, Any]:
    return {"name": entry.get("name"), "description": entry.get("description")}


def _shape_action(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": entry.get("name"),
        "risk": entry.get("risk"),
        "read_only": entry.get("read_only"),
        "allowed": entry.get("allowed"),
    }


def shape_ui_context(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten a ``fetch_context()`` envelope into the agent-facing UI view.

    Total and side-effect free: a missing or ``None`` ``ui_snapshot`` yields an
    empty page/data/buttons; missing ``actions``/``principal`` yield ``[]``/``None``.

    Args:
        raw: The ``/connector/context`` response dict.

    Returns:
        ``{page, data, buttons, actions, autonomy, principal}``.
    """
    snapshot = raw.get("ui_snapshot") or {}
    data = snapshot.get("data") or []
    buttons = snapshot.get("actions") or []
    actions = raw.get("actions") or []
    return {
        "page": snapshot.get("page"),
        "data": [_shape_data(d) for d in data if isinstance(d, dict)],
        "buttons": [_shape_button(b) for b in buttons if isinstance(b, dict)],
        "actions": [_shape_action(a) for a in actions if isinstance(a, dict)],
        "autonomy": raw.get("autonomy"),
        "principal": raw.get("principal"),
    }
```

Note: `test_shape_full_envelope` expects `data` with `truncated: False` present.
`_shape_data` only adds `truncated` when truthy, so the FULL fixture's
`"truncated": False` is dropped. Fix the fixture expectation in Step 1 to omit
`truncated` for the non-truncated row:

```python
    assert out["data"] == [{"name": "wip", "description": "WIP count", "value": 12}]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ui_context_shaper.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Format, lint, commit**

```bash
uv run black minder/core/modules/ui_context.py tests/test_ui_context_shaper.py
uv run ruff check --fix minder/core/modules/ui_context.py tests/test_ui_context_shaper.py
git add minder/core/modules/ui_context.py tests/test_ui_context_shaper.py
git commit -m "feat(modules): pure shape_ui_context helper for UI sensing"
```

---

### Task 2: Wire shaping + discovery into `read_module_context`

**Files:**
- Modify: `minder/core/modules/remote.py` (`build_module_context_spec`, ~line 480-528)
- Modify: `tests/test_module_context.py` (update the two existing tool tests + add discovery cases)

**Interfaces:**
- Consumes: `shape_ui_context` from Task 1; `ConnectorState`, `get_registry`,
  `ModuleRegistry.connector_records()`, `ModuleRegistry.get(name)` (raises `KeyError`
  when absent), `Module.manifest.display_name`.
- Produces: enhanced `read_module_context` handler. Success output:
  `{page, data, buttons, actions, autonomy, principal, state, knowledge, notes}`.
  Miss output: `{"success": False, "output": "<message + inspectable module list>"}`.

- [ ] **Step 1: Update the existing happy-path test and add discovery tests**

Replace the body of `tests/test_module_context.py` from
`test_read_module_context_merges_live_state_and_static` onward with:

```python
def test_read_module_context_shapes_ui_and_merges_static(monkeypatch, tmp_path):
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
        lambda self, **kw: {
            "autonomy": "low",
            "principal": {"username": "alice", "authenticated": True,
                          "roles": [], "scopes": []},
            "actions": [{"name": "m_tool", "risk": "low", "read_only": True,
                         "reversible": True, "undo": None, "allowed": True}],
            "ui_snapshot": {"page": "products",
                            "data": [{"name": "sku", "value": "A-1"}],
                            "actions": [{"name": "save", "description": "Save"}]},
            "state": [{"name": "inv", "value": {"n": 2}}],
        },
    )

    class _Ctx:
        principal = {"username": "alice"}
        session_id = "s1"

    spec = remote.build_module_context_spec(_Ctx())
    assert spec.name == "read_module_context"
    out = spec.handler(module_name="m")
    assert out["success"] is True
    body = out["output"]
    assert body["page"] == "products"
    assert body["data"] == [{"name": "sku", "description": None, "value": "A-1"}]
    assert body["buttons"] == [{"name": "save", "description": "Save"}]
    assert body["actions"] == [{"name": "m_tool", "risk": "low",
                                "read_only": True, "allowed": True}]
    assert body["autonomy"] == "low"
    assert body["state"][0]["name"] == "inv"
    assert body["knowledge"] == ["K1"]
    assert body["notes"] == [{"name": "a", "text": "t"}]


def test_read_module_context_unknown_module_lists_live(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="produce", connector_url="http://p:9310")
    reg.mark_connector_ready("produce", [{"name": "cmd_x"}], context={})
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="nope")
    assert out["success"] is False
    assert "produce" in out["output"]


def test_read_module_context_empty_name_lists_live(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    reg.register_connector(name="produce", connector_url="http://p:9310")
    reg.mark_connector_ready("produce", [{"name": "cmd_x"}], context={})
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="")
    assert out["success"] is False
    assert "required" in out["output"] and "produce" in out["output"]


def test_read_module_context_no_live_modules(monkeypatch, tmp_path):
    from minder.core.modules import remote
    from minder.core.modules.registry import ModuleRegistry

    reg = ModuleRegistry(tmp_path)
    monkeypatch.setattr("minder.core.modules.registry.get_registry", lambda: reg)

    class _Ctx:
        principal = None
        session_id = None

    out = remote.build_module_context_spec(_Ctx()).handler(module_name="")
    assert out["success"] is False
    assert "No modules are currently live" in out["output"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_module_context.py -q`
Expected: FAIL — the old handler returns `ui_snapshot`/raw state (no `page`/`buttons`
keys) and unknown-module output is the bare `"not reachable"` string without `produce`.

- [ ] **Step 3: Rewrite `build_module_context_spec`**

Replace the whole `build_module_context_spec` function in `minder/core/modules/remote.py`
(currently ~line 480-528) with:

```python
def _live_ui_modules(reg: Any) -> list[tuple[str, str]]:
    """READY connectors as ``(name, display_name)``; display_name best-effort."""
    from minder.core.modules.registry import ConnectorState

    out: list[tuple[str, str]] = []
    for rec in reg.connector_records():
        if rec.state is not ConnectorState.READY:
            continue
        display = rec.name
        try:
            module = reg.get(rec.name)
            if module.manifest and module.manifest.display_name:
                display = module.manifest.display_name
        except Exception:  # noqa: BLE001 — display_name is cosmetic; never fail listing
            pass
        out.append((rec.name, display))
    return out


def _inspectable_hint(reg: Any) -> str:
    """Human phrase listing the modules the agent can inspect (for miss messages)."""
    live = _live_ui_modules(reg)
    if not live:
        return "No modules are currently live to inspect."
    rendered = ", ".join(f"{name} ({display})" for name, display in live)
    return f"Modules you can inspect: {rendered}. Pass one as module_name."


def build_module_context_spec(ctx: "SkillToolContext") -> "ToolSpec":
    """A single agent tool that reads a module's LIVE on-screen UI (page, data,
    buttons, tool actions) from /connector/context, shaped for the LLM, merged
    with its static knowledge/notes. The agent calls this when asked what a module
    shows. On an unknown/unreachable module it lists what can be inspected."""
    from minder.core.skill_tools import ToolSpec  # local import: avoid cycle
    from minder.core.modules.ui_context import shape_ui_context

    def handler(**kwargs: Any) -> dict:
        from minder.core.modules.registry import ConnectorState, get_registry

        reg = get_registry()
        name = str(kwargs.get("module_name") or "").strip()
        if not name:
            return {"success": False,
                    "output": f"module_name is required. {_inspectable_hint(reg)}"}

        rec = reg.connector(name)
        if rec is None or rec.state is not ConnectorState.READY:
            return {"success": False,
                    "output": f"module {name!r} has no live UI surface. "
                              f"{_inspectable_hint(reg)}"}
        conn = RemoteConnector(rec.name, rec.connector_url)
        data = conn.fetch_context(principal=ctx.principal, session_id=ctx.session_id)
        if data is None:
            return {"success": False,
                    "output": f"module {name!r} has no live UI surface. "
                              f"{_inspectable_hint(reg)}"}
        static = rec.context or {}
        return {
            "success": True,
            "output": {
                **shape_ui_context(data),
                "state": data.get("state", []),
                "knowledge": static.get("knowledge", []),
                "notes": static.get("notes", []),
            },
        }

    return ToolSpec(
        name="read_module_context",
        description=(
            "Read a module's live on-screen UI — the current page, the data fields "
            "and values shown, the clickable buttons, and the tool actions available "
            "(with their risk and whether they're currently allowed) — plus the "
            "module's domain knowledge and area notes. Call this when the user asks "
            "what a module currently shows, or before acting on a module's UI. If you "
            "name a module that isn't live, the result lists the ones you can inspect."
        ),
        parameters={
            "type": "object",
            "properties": {
                "module_name": {
                    "type": "string",
                    "description": "The module to inspect, e.g. 'produce'.",
                }
            },
            "required": ["module_name"],
        },
        handler=handler,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_module_context.py -q`
Expected: PASS (the `_enrich_description` tests plus the 4 rewritten/added tests)

- [ ] **Step 5: Run the wider module test set to check no regression**

Run: `uv run pytest tests/test_module_context.py tests/test_remote_connector.py tests/test_remote_registry_wiring.py -q`
Expected: PASS (all)

- [ ] **Step 6: Format, lint, commit**

```bash
uv run black minder/core/modules/remote.py tests/test_module_context.py
uv run ruff check --fix minder/core/modules/remote.py tests/test_module_context.py
git add minder/core/modules/remote.py tests/test_module_context.py
git commit -m "feat(modules): shape read_module_context UI + list live modules on miss"
```

---

### Task 3: Typecheck + real end-to-end verification

**Files:** none (verification only).

**Interfaces:**
- Consumes: the enhanced tool from Task 2.
- Produces: evidence that the tool returns the shaped UI against a real running module.

- [ ] **Step 1: Typecheck the changed files**

Run: `uv run mypy minder/core/modules/ui_context.py minder/core/modules/remote.py`
Expected: no new errors in these files. Fix any that reference the new code.

- [ ] **Step 2: Full unit suite for the touched area**

Run: `uv run pytest tests/ -q -k "module_context or ui_context or remote"`
Expected: PASS.

- [ ] **Step 3: Bring up the produce module with the agent surface enabled**

```bash
# Core stack must be up first (creates the shared minder_net network).
PR_AGENT_ENABLED=1 docker compose -f modules/produce/docker-compose.yml up -d --build
# Wait for the connector to announce + go READY (one health-poll cycle).
curl -s http://localhost:9310/connector/health | python -m json.tool
```
Expected: `{"ok": true, ...}` and, within a poll cycle, produce's tools appear in the agent.

- [ ] **Step 4: Drive the agent to read the live UI (real API call)**

```bash
export OPENAI_API_KEY="$OPENAI_API_KEY"   # must be set (CLAUDE.md testing rule)
minder -p "Use read_module_context on the 'produce' module and tell me what page is open, which data fields are shown, and which buttons exist."
```
Expected: the agent calls `read_module_context(module_name="produce")` and reports a
shaped `page` + `data` + `buttons` drawn from the produce dashboard's live snapshot
(open a produce page in the browser first so a `ui_snapshot` exists for the session).

- [ ] **Step 5: Verify the discovery path (real API call)**

```bash
minder -p "Call read_module_context on a module named 'does_not_exist'."
```
Expected: the tool returns a failure whose text lists the live inspectable modules
(e.g. `produce (Produce)`), and the agent relays that list.

- [ ] **Step 6: Tear down**

```bash
docker compose -f modules/produce/docker-compose.yml down
```

---

## Self-Review

**Spec coverage:**
- Section 1 (shaped contract) → Task 1. ✅
- Section 2 (enhanced handler, preserved state/knowledge/notes, description) → Task 2. ✅
- Section 3 (discovery on empty/unknown/None, "no live modules") → Task 2 Step 3 + tests. ✅
- Section 4 (unit + real e2e) → Tasks 1–2 (unit), Task 3 (e2e). ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✅

**Type consistency:** `shape_ui_context(raw: dict) -> dict` defined in Task 1 and imported
in Task 2. Keys `page/data/buttons/actions/autonomy/principal` are identical across the
shaper, the handler output, and the tests. `_live_ui_modules`/`_inspectable_hint` are
defined and used within Task 2 only. ✅

**Known consistency note:** Task 1 Step 1's FULL fixture initially asserts
`truncated: False` is present; Step 3 corrects it to omit `truncated` for the
non-truncated row (the shaper only emits `truncated` when truthy). Apply that
correction when writing the test.
