# Design — enhance `read_module_context` UI sensing

**Date:** 2026-07-16
**Status:** Approved (brainstorming) — revised after code review
**Scope:** Single implementation plan.

## Problem

The main agent should be able to sense the live UI the user is looking at: what
page they are on, what field values are shown, what buttons/actions exist. A module
frontend declares this through the UI SDK (`minder_ui_sdk` — `setPage()` /
`setData()` / `setAction()` → a `UiSnapshot`), and the connector serves it at
`GET /connector/context` alongside autonomy, principal, and tool-action permissions.
Core pulls it via `RemoteConnector.fetch_context()` (`minder/core/modules/remote.py:285`).

**Revision (important):** a builtin agent tool for this **already exists** —
`read_module_context` (`build_module_context_spec`, `remote.py:480`). It calls
`fetch_context()` and returns the module's raw `ui_snapshot` + `state` plus static
`knowledge`/`notes`, and is auto-registered whenever ≥1 service module is READY. So
the work is **not a new tool** but two focused enhancements to this one:

1. **Shape** the raw `ui_snapshot` + context envelope into a compact, LLM-friendly
   view instead of handing over raw JSON.
2. **Discovery on miss** — when the module is unknown/unreachable, list the live
   modules the agent can inspect instead of a bare "not reachable".

## Snapshot reality (reconciliation)

The UI SDK snapshot (`agentSurface/registry.ts`) is exactly
`{ page, data: [{name, description, value, truncated?}], actions: [{name, description}] }`.
There is **no** separate "inputs/forms" field — on-screen field *values* are `data`,
and clickable controls are the snapshot's `actions` (buttons). Separately, the
`/connector/context` envelope carries top-level `actions:
[{name, risk, read_only, reversible, undo, allowed}]` (the module's tool actions and
whether the current autonomy allows them), plus `autonomy`, `principal`
`{username, authenticated, roles, scopes}`, and `state`.

## Section 1 — Shaped contract

Add a pure function `shape_ui_context(raw: dict) -> dict` that flattens the
`fetch_context()` envelope into:

- `page` — `ui_snapshot.page` (or `None`)
- `data` — on-screen field values from `ui_snapshot.data` (`name`, `description`, `value`, `truncated?`)
- `buttons` — clickable UI controls from `ui_snapshot.actions` (`name`, `description`)
- `actions` — the module's tool actions from the top-level `actions`, trimmed to
  `name`, `risk`, `read_only`, `allowed` (what the agent may do here)
- `autonomy` — the caller's autonomy level
- `principal` — `{username, authenticated, roles, scopes}`

Pure and total: a missing/`None` `ui_snapshot` yields `page: None, data: [], buttons: []`;
missing `actions`/`principal` yield `[]`/`None`. No exceptions. Unit-testable in isolation.

## Section 2 — Enhanced `read_module_context`

Modify `build_module_context_spec` (`remote.py:480`):

- On success, return
  `{**shape_ui_context(data), "state": data.get("state", []), "knowledge": …, "notes": …}`.
  `state`, `knowledge`, and `notes` are preserved (no regression); the UI surface is
  now shaped rather than raw.
- Principal/session are already threaded via `ctx.principal` / `ctx.session_id` — unchanged.
- Update the tool description to say it returns the shaped page/data/buttons/actions view.

No `registry.py` change and no builtin-schema-file change: the tool is a dynamically
built `ToolSpec` (via `build_remote_tool_specs`), not a static builtin schema.

## Section 3 — Discovery & error behavior

Add a registry helper `_live_ui_modules(reg) -> list[tuple[name, display_name]]`
listing READY connectors (display_name best-effort from `reg.get(name).manifest`,
falling back to the connector name). Then in the handler:

- **Empty `module_name`** → `success: false`, message "module_name is required" plus
  the inspectable-modules list.
- **Unknown / not READY / `fetch_context()` returns None** → `success: false`, message
  "module `X` has no live UI surface" plus the inspectable-modules list. When nothing is
  live: "No modules are currently live to inspect."

A blind first call thus teaches the agent what it can inspect. No separate discovery tool.

## Section 4 — Testing

Per CLAUDE.md: unit **and** real end-to-end.

- **Unit** (`uv run pytest`):
  - `shape_ui_context()` — full envelope → shaped contract; `None` ui_snapshot;
    missing `actions`/`principal`; truncated data flag preserved.
  - `build_module_context_spec` handler (extend `tests/test_module_context.py`):
    happy path returns shaped `page/data/buttons/actions` + preserved
    `state/knowledge/notes`; unknown module → `success:false` listing live modules;
    empty `module_name` → listing; no live modules → "No modules are currently live".
- **End-to-end** (real run, `OPENAI_API_KEY` set): bring up the `produce` module with
  `PR_AGENT_ENABLED=1` (Track B, live UI surface), run the agent, confirm
  `read_module_context(module_name="produce")` returns the actual shaped page/data/
  buttons the dashboard declared.

## Non-goals

- No new tool — enhance the existing `read_module_context`.
- No writing/driving the UI (that is the existing `agentDriver` / UI-intent path).
- No new SDK or `minder_ui_sdk` changes — the snapshot contract already exists.
- No `registry.py` or builtin-schema-file changes (the tool is a dynamic `ToolSpec`).

## Key files

- `minder/core/modules/remote.py:480` — `build_module_context_spec` (enhanced).
- `minder/core/modules/ui_context.py` — new `shape_ui_context()` pure helper.
- `minder/core/modules/registry.py` — `ConnectorState`, `connector_records()`, `get()`.
- `minder_ui_sdk/src/agentSurface/registry.ts` — reference for the snapshot shape.
- `tests/test_module_context.py` — existing tests to extend.
