# Design — `get_ui_context` builtin tool

**Date:** 2026-07-16
**Status:** Approved (brainstorming)
**Scope:** Single implementation plan.

## Problem

The main agent is blind to the live UI the user is looking at. A module frontend
already declares its page, data fields, and action controls through the UI SDK
(`minder_ui_sdk` — `setPage()` / `setData()` / `setAction()` → a `UiSnapshot`),
and the connector serves it at `GET /connector/context` (page, data, actions,
autonomy, principal, live state). Core can already pull that snapshot via
`RemoteConnector.fetch_context()` (`minder/core/modules/remote.py:285`).

What is missing is an **agent-facing builtin tool** that reads it. The data is one
method call away, but no entry in `ToolRegistry` exposes it, so the agent cannot
sense what page / buttons / inputs the user currently has on screen.

## Model

Like skills: each live module already injects its tool schemas and `SKILL.md`
guidance, so the agent knows *which* modules exist. It just needs a way to
**actively read the live UI state** of one. This is one read-only builtin tool the
agent calls with a module id, plus cheap discovery baked into the tool itself.

## Section 1 — Tool surface & contract

A single new builtin tool registered in `ToolRegistry`:

```
get_ui_context(module: str) -> dict
```

- **Input:** `module` — the module id whose live page to sense (e.g. `"produce"`).
- **Behavior:** calls `RemoteConnector.fetch_context()` for that module and returns
  a compact, LLM-shaped view of the current UI:
  - `page` — active route/page name the user is on
  - `data` — declared data fields (name → description → current value), from `setData()`
  - `actions` — buttons/controls available (name, description, risk, allowed), from `setAction()`
  - `inputs` / `forms` — declared form fields the agent could fill (from `ui_snapshot`)
  - `autonomy` + `principal` — who is acting and at what autonomy level
- **Read-only.** No side effects, no approval gating. Pure sensing.

Output is trimmed and flattened (not raw JSON) so it is cheap in tokens and directly
usable by the model to reason about what is on the user's screen. `inputs/forms` and
`actions` are both in scope.

## Section 2 — Implementation shape

Follows the existing builtin-tool pattern (handler + registry entry); no new
infrastructure.

1. **Handler** — `handlers/ui_context_handler.py`, a small `UiContextHandler` class
   with `get_ui_context(args, ctx=None)`, mirroring `AskUserHandler` /
   `MessageToolHandler`.
2. **Resolution** — the handler needs the module store to obtain a `RemoteConnector`.
   The registry already holds module/skill wiring (`_skill_specs`), so the handler
   receives the module-lookup callable injected the same way skill handlers do. It
   calls `connector.fetch_context(principal=…, session_id=…)`, threading the current
   principal/session from the tool context (same as remote tools already do).
3. **Shaper** — a pure function `shape_ui_context(raw: dict) -> dict` that trims the
   raw `fetch_context()` payload down to the Section 1 contract
   (`page/data/actions/inputs/autonomy/principal`). Pure and unit-testable in
   isolation.
4. **Registration** — one line in `registry.py`:
   `self._handlers["get_ui_context"] = self._ui_context_handler.get_ui_context`,
   plus the JSON schema/description registered alongside the other builtin tool specs
   so the model sees it.

Result dict is the standard envelope `{success, output, error}` where `output` is the
shaped context (the agent-visible payload).

## Section 3 — Discovery & error behavior

The agent explores actively, so the tool makes discovery cheap without a second tool:

- **Unknown or empty `module`** → `success: false`, `output` **lists the currently-live
  modules that expose a UI surface** (name + display_name). A blind first call teaches
  the agent what it can inspect.
- **Live but no UI context declared** (Track-A module, or no `agentSurface` registry)
  → `success: true`, `output` states "no live UI surface declared" plus whatever static
  manifest info exists — never an error.
- **Connector unreachable/dead** → `success: false`, `output` says the module is down
  (fail-closed, matching how dead connectors are handled elsewhere).

No separate `list_ui_modules` tool — discovery is via the unknown-module error path.

## Section 4 — Testing

Per CLAUDE.md: unit **and** real end-to-end.

- **Unit** (`uv run pytest`):
  - `shape_ui_context()` — full snapshot → trimmed contract; missing fields; empty snapshot.
  - Handler with a faked module store: happy path; unknown module → lists live modules;
    dead connector → fail-closed; live-but-no-UI → graceful `success:true`.
  - Registry dispatch: `get_ui_context` resolves and returns the envelope.
- **End-to-end** (real run, `OPENAI_API_KEY` set): bring up the `produce` module (live
  UI surface via `minder_ui_sdk`), run the agent, confirm `get_ui_context("produce")`
  returns the actual page/data/actions the dashboard declared.

## Non-goals

- No writing/driving the UI (that is the existing `agentDriver` / UI-intent path).
- No new SDK or `minder_ui_sdk` changes — the snapshot contract already exists.
- No separate discovery tool.

## Key files

- `minder/core/modules/remote.py:285` — `fetch_context()` (reused as-is).
- `minder/core/context_engineering/tools/registry.py` — register the tool.
- `minder/core/context_engineering/tools/handlers/ui_context_handler.py` — new handler.
- `minder_ui_sdk/src/agentSurface/registry.ts` — reference for the snapshot shape.
