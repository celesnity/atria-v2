# Agent Declarative UI Wrapper (`Agent.*`) — Design

**Date:** 2026-07-13
**Status:** Approved (design), pending implementation plan
**Package:** extends `minder_ui_sdk`

## Problem

`minder_ui_sdk` already lets an agent read committed events (`useModuleEvents`),
read autonomy/permission context (`useAgentContext`), and drive UI through a typed
intent bus (`useAgentForm` + `data-agent-*` attributes over `/connector/ui/intents`).

What is missing is a **declarative, component-level façade** so a module author can
simply *wrap* a piece of UI and have the agent understand it:

- wrap a button → give it a name + description → agent knows what it does and can trigger it
- wrap a data component → agent can **read** what is currently on screen
- wrap a page → agent knows **which page** it is looking at

Today this requires manually sprinkling `data-agent-*` attributes and wiring
`useAgentForm`. We want a clean wrapper API on top of the existing SSE infrastructure —
**no new transport**.

## Goals

- Three transparent wrapper components: `Agent.Page`, `Agent.Data`, `Agent.Button`.
- A browser-side **registry** that is the source of truth for "what the agent sees on
  this page" (current page, readable data, invokable actions).
- Agent can **read** a snapshot of the page and **act** (trigger a wrapped button's
  handler) — both bidirectional, per the user's requirement.
- Reuse the existing `/connector/ui/intents` (act) and connector snapshot channel (read).
  No new transport layer.

## Non-Goals

- No approval / human-in-the-loop for `Agent.Button` actions. Per decision, `onAct`
  **runs immediately** when the agent invokes it. If a module needs a gate, it wraps
  that logic inside its own handler. (The existing `DecisionPacket` / `useAgentForm`
  flow remains available separately for modules that want it.)
- Not replacing `useAgentForm` / `data-agent-*`. `Agent.*` is a higher-level layer;
  both coexist.
- No visual styling — wrappers render children verbatim.

## Decisions (resolved)

- **API shape:** wrapper components (`<Agent.Button>`, `<Agent.Data>`, `<Agent.Page>`),
  not hooks/attributes.
- **Transport:** reuse existing SSE intents/events + connector snapshot channel.
- **Approval:** none — `onAct` fires immediately.
- **Naming:** action/data names are **scoped by the enclosing `Agent.Page`**, e.g.
  `products.add_product`. Avoids collisions naturally.
- **Snapshot value size:** cap each `Agent.Data` value at ~32 KB serialized. If larger,
  truncate and set a `truncated: true` flag so the agent knows the view is partial.

## Architecture

```
Module JSX
  <Agent.Page name="products" ...>
    <Agent.Data name="products" value={rows}> <ProductTable/> </Agent.Data>
    <Agent.Button name="add_product" onAct={handleAdd}> <button/> </Agent.Button>
  </Agent.Page>
        |  register / update / unregister
        v
AgentRegistryProvider (browser, mounted inside defineDashboard)
  - currentPage
  - data:    Map<name, {description, value}>
  - actions: Map<name, {description, onAct}>
        |                                   ^
   (read) push snapshot                     | (act) intent {intent:'act', name}
        v                                   |
   /connector snapshot channel      /connector/ui/intents  (existing SSE bus)
        |                                   |
        v                                   v
   backend cache  ---->  agent      AgentDriverProvider dispatches 'act' → registry.run(name)
   (agent reads snapshot alongside context)
```

### Components

All three are **transparent**: they register into the registry and render
`children` unchanged. No wrapper DOM/styling beyond what's needed for presence targeting.

**`Agent.Page`**
- Props: `name: string`, `description?: string`, `children`.
- Effect: sets `currentPage = name` while mounted; provides a React context that scopes
  child names to `${page}.${childName}`.
- Multiple pages can technically mount, but the intended use is one active page per view
  (matches the host's `activeTab` model). Registry tracks the most-recently-active page.

**`Agent.Data`**
- Props: `name: string`, `description?: string`, `value: unknown`, `children`.
- Effect: registers `{fullName, description, value}`. On `value` change, updates the
  registry entry and schedules a snapshot push (debounced ~150 ms). Unregisters on unmount.
- Value serialization guarded by the 32 KB cap + `truncated` flag.

**`Agent.Button`**
- Props: `name: string`, `description?: string`, `onAct: () => void | Promise<void>`, `children`.
- Effect: registers `{fullName, description, onAct}`. Unregisters on unmount.
- Auto-attaches `data-agent-control={fullName}` to the wrapped subtree root so the
  existing ghost cursor / Mascot presence layer points at the right control when the
  agent acts — no changes to the presence layer.

### Registry (`AgentRegistryProvider`)

- Mounted **inside `defineDashboard`** so modules get it for free (no extra setup).
- Holds `currentPage`, `data` map, `actions` map.
- `run(name)` looks up an action and calls its `onAct` immediately.
- `snapshot()` serializes `{page, data:[{name,description,value,truncated?}], actions:[{name,description}]}`.
- Pushes snapshot on: page mount, page change, and debounced data change.

### Data flow

**Read (agent ← UI):**
1. Registry builds a snapshot and pushes it to the connector snapshot channel.
2. Backend caches the latest snapshot per session/module.
3. Agent reads it (surfaced the same way `useAgentContext` context is fetched — a
   `/connector/context`-style read, extended to include `ui_snapshot`).

**Act (agent → UI):**
1. Agent emits `{ intent: 'act', name: 'products.add_product' }` on the existing
   `/connector/ui/intents` SSE bus.
2. `AgentDriverProvider` (already subscribed) recognizes the new `act` intent variant
   and calls `registry.run(name)`.
3. `onAct` runs immediately; the resulting real action (e.g. an API call that emits an
   `action.completed` event) flows back through the existing event stream + presence layer.

The **only** new wire-level addition is one intent variant: `{ intent: 'act'; name: string }`.

## Integration points (existing code)

- `defineDashboard` (`minder_ui_sdk/src/index.ts`) — mount `AgentRegistryProvider`.
- `AgentDriverProvider` — handle the new `act` intent variant → `registry.run`.
- Connector context read — include `ui_snapshot` in the payload the agent fetches.
- Presence layer (ghost cursor / Mascot) — unchanged; benefits automatically from the
  `data-agent-control` attribute `Agent.Button` attaches.
- `useAgentForm` / `data-agent-*` — untouched; coexist.

## Error handling

- **Duplicate name within a page:** last registration wins; emit a `console.warn` in dev.
- **Act on unknown name:** no-op + `console.warn`; agent-visible snapshot only ever lists
  real actions, so this is a defensive guard.
- **`onAct` throws:** caught; the error surfaces through the normal module error/event path,
  not swallowed silently.
- **Oversized `value`:** truncated to 32 KB, `truncated: true` set; never blocks the push.
- **Unmount race:** registry entries keyed by a stable id; unregister is idempotent.

## Testing

Per `CLAUDE.md`, both unit **and** real end-to-end are required.

**Unit (Vitest):**
- Rendering `Agent.Data` registers an entry with correct scoped name + value; changing
  `value` updates the snapshot; unmount removes it.
- Rendering `Agent.Button` registers an action; `registry.run(name)` calls `onAct`.
- `Agent.Page` scopes child names (`page.child`).
- Snapshot serialization respects the 32 KB cap and sets `truncated`.
- Duplicate-name warning; act-on-unknown-name no-op.

**End-to-end (real API, in `module_template`):**
- Wrap one panel of `module_template` with `Agent.Page` / `Agent.Data` / `Agent.Button`.
- Run the host (`minder run ui`), issue a real agent turn that (a) reads the snapshot to
  answer a question about on-screen data, and (b) acts a wrapped button.
- Confirm the wrapped `onAct` handler actually ran and the ghost cursor pointed at the
  control.

## Open items for the implementation plan

- Exact shape of the connector snapshot endpoint (new sub-path vs. extending
  `/connector/context`).
- Debounce timing and whether snapshot pushes should coalesce across multiple `Agent.Data`
  updates in one render.
- TypeScript surface: `Agent` namespace object vs. named exports (`AgentPage`, etc.).
