# Agent Declarative Backend Context (`@conn.context.*`) — Design

**Date:** 2026-07-13
**Status:** Approved (design), pending implementation plan
**Package:** extends `minder_module_sdk`

## Problem

The frontend now has a declarative `Agent.*` wrapper layer (see
`2026-07-13-agent-declarative-ui-wrapper-design.md`) that lets a module author *wrap*
UI so the agent can read on-screen data and act. The backend `Connector` has no
symmetric way to **declare context** for the agent: today, context is only *implicit*
in tool metadata (`risk`, `reversible`, `undo`), the Operational Graph provider, the UI
snapshot, and principal/autonomy. A module author cannot say, declaratively:

- "here is live module state the agent should read" (mirror of `Agent.Data`)
- "here is domain knowledge / a guardrail the agent must respect"
- "here is what this page/area is for" (mirror of `Agent.Page`)
- "here is when to use this action, with examples" (richer action semantics)

This design adds a decorator family `@conn.context.*` — a **backend mirror of the
frontend `Agent.*` layer** — that assembles an explicit agent-facing context surface.

## Goals

- One decorator namespace `conn.context.*` (chosen over separate top-level decorators).
- Four declaration kinds:
  1. `@conn.context.state(name, description)` — decorate a function returning **live**
     module state; evaluated on every context read; may receive `principal` / `session_id`.
  2. `conn.context.knowledge(text)` — static domain knowledge / guardrail strings.
  3. `conn.context.note(name, text)` — static labeled area/page descriptions.
  4. `when_to_use=` and `examples=` kwargs added to the existing `@conn.tool` /
     `@conn.read` decorators — richer action semantics.
- Surface the **static** parts (`knowledge`, `notes`, tool `when_to_use`/`examples`) in
  `GET /connector/manifest` (cacheable, read once at discovery — good for prefix caching
  per `2026-07-04-minder-agent-latency-context-optimization-design.md`).
- Surface the **dynamic** part (`state`) in `GET /connector/context`, evaluated live.
- No new transport. No change to how tools are invoked or gated.

## Non-Goals

- Not replacing the Operational Graph (`@conn.graph`) — graph answers *linked* context
  queries; `context.state` is a flat always-on state snapshot. They coexist.
- Not replacing `conn.page` / `conn.form` / `conn.control` (the UI surface). `context.note`
  is free-form agent-facing prose, not a navigable page; `conn.page` stays as-is.
- No caching/TTL layer for `state` — it evaluates live on every context read (chosen).
- No dynamic (function-based) `knowledge`/`note` — static strings only (YAGNI).

## Decisions (resolved)

- **Namespace:** a single `conn.context.*` family.
- **State evaluation:** live on every `GET /connector/context`, fail-closed per entry;
  may receive `principal` / `session_id` via the existing `_accepts_arg` injection.
- **Static/dynamic split:** `knowledge` + `note` + tool `when_to_use`/`examples` → manifest;
  `state` → context.
- **Tool enrichment:** additive kwargs on the existing `@conn.tool` / `@conn.read`
  (not a separate `@conn.context.guidance`).
- **Value cap:** each `state` value capped at 32768 serialized characters, over-cap →
  truncated with `truncated: true` (consistent with frontend `Agent.Data`).

## Architecture

```
Module (app.py)
  @conn.context.state("inventory", "...")   def inventory_state(principal=None): ...
  conn.context.knowledge("Always check MEL before dispatch.")
  conn.context.note("products", "Product catalog area — add/restock/delete.")
  @conn.tool("create_product", when_to_use="...", examples=[...])   def create_product(...): ...
        |
   Connector holds:
     self._ctx_state:     dict[str, _StateProvider]   # name -> {description, fn}
     self._ctx_knowledge: list[str]
     self._ctx_notes:     list[Note]                  # {name, text}
     _Tool gains: when_to_use: str = "", examples: list = []
        |
   ┌────────────────────────────┬─────────────────────────────┐
   v                            v
 GET /connector/manifest      GET /connector/context
   "context": {                 ...existing (autonomy, principal, actions, ui_snapshot)...
     "knowledge": [...],        "state": [ { name, description, value, truncated? } ]
     "notes": [ {name,text} ]       (each state fn called live, principal injected)
   },
   "tools": [ { ..., when_to_use, examples } ]
```

### The `conn.context` accessor

`conn.context` is a small namespace object attached to `Connector` (a
`_ContextRegistrar` bound to the connector instance). It exposes:

- `state(name: str, description: str = "") -> Callable[[Callable], Callable]` — decorator;
  registers `self._ctx_state[name] = _StateProvider(description=description, fn=fn)` and
  returns `fn` unchanged.
- `knowledge(text: str) -> None` — appends to `self._ctx_knowledge` (ignores empty/blank).
- `note(name: str, text: str) -> None` — appends `Note(name, text)` to `self._ctx_notes`
  (ignores empty; duplicate `name` overwrites the prior note + warns).

### State provider evaluation

On `GET /connector/context`, for each registered state provider:
- Build kwargs by the existing `_accepts_arg(fn, "principal")` / `_accepts_arg(fn,
  "session_id")` mechanism (same as tools and the graph provider), passing the request's
  parsed `Principal` and session.
- Call `fn(**kwargs)`; serialize the return; apply the 32768-char cap.
- On exception: skip that entry, `logger.warning("context.state %r failed: %s", name, exc)`,
  continue with the rest (fail-closed per entry — never breaks the whole context response).

Result shape per entry: `{"name": str, "description": str, "value": <any>, "truncated"?: bool}`.

### Tool enrichment

`_Tool` dataclass gains `when_to_use: str = ""` and `examples: list = field(default_factory=list)`.
`@conn.tool` / `@conn.read` accept `when_to_use: str = ""` and `examples: Optional[list] = None`
and store them. The manifest's per-tool dict includes both (omitted or empty when unset).
No effect on invocation, validation, or gating.

## Data flow

- **Static (discovery-time):** Core reads `GET /connector/manifest` once when it discovers
  the module. The new `context.knowledge`, `context.notes`, and per-tool
  `when_to_use`/`examples` ride along — cached with the rest of the manifest, no per-turn cost.
- **Dynamic (plan-time):** Core reads `GET /connector/context` before planning (as it does
  today for autonomy/principal/actions/ui_snapshot). The new `state[]` array is evaluated
  live there, so the agent always sees current module state.

## Error handling

- **State provider throws:** entry dropped, warning logged, other entries still returned.
- **Duplicate `state`/`note` name:** last registration wins; `logger.warning`.
- **Empty/blank `knowledge`/`note` text:** ignored (not registered).
- **Oversized state value:** truncated to 32768 chars, `truncated: true`; never blocks.
- **Non-JSON-serializable state value:** fall back to `str(value)` before capping (mirrors
  the frontend registry's `capValue`).

## Testing

Per `CLAUDE.md`, both unit and real end-to-end are required.

**Unit (pytest — `conn.invoke` / `TestClient(conn.asgi())`, matching
`minder_module_sdk/tests/` conventions):**
- `@conn.context.state` registers a provider; `GET /connector/context` returns its live
  value; the provider receives `principal` when it declares that arg.
- A state provider that raises is skipped and does not break the context response
  (other state entries + the rest of the payload still present).
- Oversized state value is truncated with `truncated: true`.
- Duplicate `state`/`note` name overwrites + is the only one present.
- `conn.context.knowledge(...)` and `conn.context.note(...)` appear under
  `manifest["context"]`; empty strings are ignored.
- `@conn.tool(..., when_to_use=..., examples=[...])` surfaces both in the manifest tool
  entry; a tool without them omits/empties them; invocation/gating unchanged.

**End-to-end (real run, in `module_template`):**
- Add a `context.state` (e.g. inventory summary from the products store), a
  `context.knowledge` guardrail, a `context.note` for the products area, and
  `when_to_use`/`examples` on `create_product`.
- Run the module; `GET /connector/manifest` and `GET /connector/context` (with a principal
  header) and confirm the declared context is present and the state value is live.

## Open items for the implementation plan

- Exact placement of the `context` key in the manifest dict (top-level vs nested).
- Whether `_ContextRegistrar` is a nested class or a lightweight `types.SimpleNamespace`
  of bound methods — pick whichever matches the connector's existing style.
- Public export surface (`Note` dataclass) from `minder_module_sdk` package `__init__`.
