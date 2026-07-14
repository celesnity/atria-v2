# Minder Core Consumes Module Declarative Context — Design

**Date:** 2026-07-14
**Status:** Approved (design), pending implementation plan
**Package:** `minder/core` (consumer side)

## Problem

Two declarative context layers now ship in the SDK — frontend `Agent.*`
(pushes `ui_snapshot`) and backend `@conn.context.*` (exposes `state` /
`knowledge` / `notes` and per-tool `when_to_use` / `examples`). The live
connector endpoints return all of this (verified in docker). But **Minder core
never consumes it**: `build_remote_tool_specs` reads only a tool's
`name`/`description`/`parameters`/`streaming`, core never calls
`/connector/context`, and the agent's prompt only carries each module's
`SKILL.md`. As a result the agent can *act* on a module (it has the tools) but
cannot *see* the module — asked "what's in this module right now?" it answers
"I can't see the page."

This design makes core **consume** the declarative context so the agent can see
integrated modules.

## Goals

- **Light static injection into the prompt** (no network at prompt-build time):
  each module's `knowledge` + `note` names go into its `SKILL.md` block, plus a
  one-line hint that live state is available via a tool. All modules (no
  active-module scoping).
- **On-demand detail tool**: `read_module_context(module_name)` returns the
  module's full live `state` values, `ui_snapshot`, `knowledge`, and `notes`.
  The agent calls it when the user asks about a module's current state.
- **Richer tool schemas**: fold each proxy tool's `when_to_use` + `examples`
  into the `description` the LLM sees, so the agent picks/understands tools better.
- Capture the manifest `context` block into the connector registry record at
  reconcile time, so the static prompt injection reads from cache (no extra
  network).

## Non-Goals

- No active-module scoping — knowledge/notes for every module go into the prompt
  (they are short). Scoping to "the module the user is viewing" is deferred (YAGNI).
- No live `state`/`ui_snapshot` in the prompt — that stays dynamic behind the
  tool, so prompt-build never blocks on a network call.
- No change to how tools are invoked or gated; no new connector endpoints
  (core only *reads* what the SDK already exposes).

## Decisions (resolved)

- Mechanism: **both** — light static list in prompt + on-demand detail tool.
- Fold `when_to_use`/`examples` into proxy tool `description` (piece C): **yes**.
- Prompt injection scope: **all modules**, static `knowledge`/`notes` only.
- Static context source: captured onto the connector registry record from the
  **live** manifest (which core already fetches for tool specs) — not the
  committed `manifest.json`, and not a fresh network call at prompt time.

## Architecture

Four pieces, all in `minder/core`:

**A. `RemoteConnector.fetch_context()`** — `minder/core/modules/remote.py`
New method: `GET /connector/context` with the module's auth/principal/session
headers (same header helper `call_tool` uses). Returns the parsed dict
(`state`, `knowledge`, `notes`, `ui_snapshot`, `actions`) or `None` on HTTP/parse
error (fail-soft, like `fetch_manifest`).

**B. Agent tool `read_module_context(module_name)`** — registered in the tool layer
Resolves the module in the registry, builds a `RemoteConnector`, calls
`fetch_context()`, and returns a compact result: `{state, ui_snapshot,
knowledge, notes}`. Module not found / offline → a clear error string, never
raises. This is the "detail on demand" path the agent invokes when asked about a
module's current state.

**C. Fold `when_to_use` + `examples` into proxy tool descriptions** —
`build_remote_tool_specs()` in `remote.py`
When building each `ToolSpec`, append the tool's `when_to_use` (as a
"When to use: …" line) and `examples` (as a short "Examples: …" block) to
`description`. Both come from the manifest tool dict already fetched. Empty →
appended nothing. The LLM now sees richer per-tool guidance.

**D. Inject module `knowledge` + `notes` into the SKILL block** —
`render_module_section()` in `minder/core/modules/prompt.py`
After the existing name/description/when-to-use/subskills lines, if the module's
connector record carries a `context`, append:
- a `**Domain knowledge:**` bullet list of `knowledge` strings,
- a `**Areas:**` bullet list of note `name` (with `text`),
- one hint line: *"Call `read_module_context('<name>')` for live state and the
  current on-screen snapshot."*
Modules without SDK context render exactly as today.

**Supporting change — capture `context` onto the connector record.**
Wherever the module/connector registry reconciles a connector and stores its
live-manifest `tools` on the record, also store `record.context =
manifest.get("context")` (the `{knowledge, notes}` block). Pieces C reads tool
enrich straight from the manifest tool dicts it already iterates; piece D reads
`record.context`. No new network path; prompt build stays offline.

## Data flow

- **Reconcile time (already happens):** core fetches each READY connector's live
  `/connector/manifest` to build tool specs. Now it also (i) folds
  `when_to_use`/`examples` into each proxy tool description (C), and (ii) stashes
  the manifest `context` block on the connector record (support for D).
- **Prompt-build time (offline):** the SKILL block renders each module's static
  `knowledge`/`notes` from its connector record + the "call the tool" hint (D).
- **Turn time (on demand):** when the user asks about a module's live state, the
  agent calls `read_module_context(module_name)`, which hits `/connector/context`
  and returns live `state` + `ui_snapshot` + `knowledge` + `notes` (A + B).

## Error handling

- `fetch_context` HTTP/timeout/parse error → returns `None`.
- `read_module_context`: unknown module → `{"error": "module <name> not found"}`;
  offline/None → `{"error": "module <name> is not reachable"}`. Never raises.
- Connector record without a `context` block (non-SDK or older module) → piece D
  adds nothing; piece C appends nothing when `when_to_use`/`examples` are empty.
- Reconcile capturing `context` is wrapped so a malformed manifest never blocks
  tool registration (matches the existing `try/except` around remote registration).

## Testing

Per `CLAUDE.md`, unit **and** real end-to-end.

**Unit (pytest):**
- `fetch_context` returns the parsed dict on 200 and `None` on error (mock the client).
- `build_remote_tool_specs` folds `when_to_use`/`examples` into `description`; a
  tool without them keeps its plain description.
- The connector record stores the manifest `context` block after reconcile.
- `render_module_section` includes knowledge/notes + the tool hint when the record
  has context, and is unchanged when it does not.
- `read_module_context` returns state/ui_snapshot/knowledge/notes for a known
  module and a soft error for unknown/offline.

**End-to-end (real, docker already running):**
- With `module_template` up, run a real agent turn asking "what does module_template
  have right now?" and confirm the agent calls `read_module_context` and reports the
  live inventory/jobs state and the product notes.
- Confirm the agent's tool list shows `create_product` etc. with the folded
  `when_to_use`/`examples` guidance, and that the prompt carries the module's
  knowledge/notes (inspect the composed system prompt or a debug dump).

## Open items for the implementation plan

- Exact type/field to add for `record.context` on the connector registry record,
  and the precise reconcile function that populates `record.tools` (to co-locate).
- Which tool-registration seam hosts `read_module_context` (an inline tool mixin
  vs. a dedicated handler) and how it accesses the module registry + principal.
- The exact auth/header helper `fetch_context` should reuse from `call_tool`.
