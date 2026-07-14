# minder_ui_sdk — ag-ui-inspired protocol upgrade

**Date:** 2026-07-15
**Status:** Approved design, pre-implementation
**Scope:** TypeScript `minder_ui_sdk` + Python `minder_python_sdk` connector (end-to-end)

## Motivation

An audit of the [ag-ui protocol](https://github.com/ag-ui-protocol/ag-ui) against
our home-grown `minder_ui_sdk` surfaced four borrowable ideas that fix concrete
inefficiency and correctness gaps in code we already ship. ag-ui as a whole
solves a different problem (streaming an agent's own chat/tool output as an RxJS
Observable); our SDK is about the **agent and human sharing a real module UI**
(sense the screen, drive real forms, approve decisions). Most of ag-ui does not
apply. The four ideas that do:

1. **State delta via JSON Patch** — `AgentSurface` currently POSTs the *entire*
   snapshot on every data change. ag-ui's snapshot-once + RFC-6902 deltas is a
   direct bandwidth win.
2. **Enveloped events end-to-end** — module events are already enveloped on the
   Python side, but `UiIntent`s are raw dicts with no `event_id`/`ts`, so the
   driver cannot dedup, order, or safely replay after a reconnect.
3. **Runtime validation at the boundary** — both consumers do
   `JSON.parse(...) as UiIntent`, a lie to the type system; a malformed `submit`
   intent flows straight into real form controllers.
4. **One multiplexed stream** — we open a separate `EventSource` per concern
   (`/connector/events` and `/connector/ui/intents`), each with independent
   reconnect/race behavior. ag-ui multiplexes everything on one typed stream.

Deliberately **out of scope** (over-engineering for our scale): RxJS Observable
core, protobuf transport, A2UI generative UI. These were considered and rejected.

## Decisions (locked)

- **Reach:** both the TS SDK and the Python connector — a real end-to-end change.
- **Compatibility posture:** **clean cut.** The SDK is `0.1.0`/private and the
  connector ships to a small set of first-party modules. We replace wire shapes
  outright rather than maintaining dual paths. Requires a lockstep rebuild of the
  modules and the committed `minder/web/static` bundle (a known deploy footgun —
  see repo hygiene notes).
- **Validation:** **Zod.** Robust discriminated-union schemas outweigh the cost
  of one new runtime dependency in a currently dep-free SDK.
- **#4 mechanism:** a **ref-counted shared-`EventSource` singleton** keyed by URL,
  not a new provider component. Keeps the existing hook signatures; one physical
  connection per URL; auto-closed on last unsubscribe.

## Architecture

Two channels, one envelope.

### Channel A — backend→browser SSE (delivers #2 + #4)

A single endpoint replaces both existing SSE endpoints:

```
GET /connector/stream?session={sessionId}
```

It emits **all** `EventEnvelope`s relevant to that session:

- Module domain events (`action.invoked`, `action.completed`, `queue.changed`, …)
- `ui.intent` envelopes (the agent driving the UI)

Session filtering: envelopes with a `session_id` are delivered only to matching
subscribers; envelopes with no `session_id` (broadcasts) go to all. Consumers
filter by `type`. `push_ui_intent()` already dispatches a `ui.intent` **envelope**
to the event listeners today, so intents arriving enveloped on this stream is a
natural fit, not a bolt-on.

`/connector/events` and `/connector/ui/intents` are **removed**.

### Channel B — browser→backend POST (delivers #1)

The `AgentSurface` snapshot channel keeps its endpoint but changes its body:

```
POST /connector/ui/snapshot
```

- First push (and after any reset): full snapshot.
- Subsequent pushes: RFC-6902 JSON Patch delta against the last-sent snapshot.

The backend applies patches to the stored snapshot. The **agent read path is
unchanged** — `GET /connector/context` still returns the full current
`ui_snapshot`. Delta is purely a browser→backend transport optimization.

## Wire contracts

### Envelope (now parsed in the browser too)

```
EventEnvelope<P> = {
  event_id: string
  type: string
  module: string
  ts: string
  source: string
  actor?: { kind: 'agent'|'human'|'system', agent_id?, on_behalf_of? } | null
  session_id?: string | null
  payload: P
}
```

### Intent (rides as the payload of a `ui.intent` envelope)

The `UiIntent` union is unchanged in shape
(`navigate`/`fill`/`focus`/`highlight`/`request_confirm`/`submit`/`act`), but now
it is always carried as `envelope.payload` of a `type: "ui.intent"` envelope.
Because the envelope carries `event_id` + `ts`:

- **Dedup:** the driver keeps a bounded `Set` of seen `event_id`s (ring buffer)
  and drops replays delivered after an `EventSource` reconnect.
- **Ordering:** single ordered stream + arrival order; dedup guards replays.
- The existing client-side `tick` counter is retained **only** for mascot
  re-animation on a repeated intent — it is no longer load-bearing for
  correctness.

### Snapshot POST (optimistic versioning)

Versioning lets a delta survive a lost backend baseline (backend restart, etc.):

```
// full
{ session_id, kind: 'snapshot', version: N, snapshot: { page, data[], actions[] } }

// delta
{ session_id, kind: 'delta', base_version: N, delta: [ ...RFC6902 ops ] }
```

Backend stores `{ version, snapshot }` per session. On a delta whose
`base_version` does not equal the stored `version`, the backend responds **409**;
the client resends a full snapshot with a fresh version. Malformed body → **422**.

## Components

### TypeScript SDK (`minder_ui_sdk`)

- `src/events.ts` **(new)** — Zod schemas: `EventEnvelopeSchema`,
  `UiIntentSchema` (discriminated union on `intent`), `SnapshotSchema`. Exported
  `parseEnvelope` / `parseUiIntent` helpers returning `safeParse` results. Event
  `type` constants (e.g. `UI_INTENT = 'ui.intent'`).
- `src/stream.ts` **(new)** — `getSharedStream(url)`: a module-level
  `Map<url, { es, subscribers, refCount }>`. Returns `{ subscribe(fn), close() }`;
  opens one `EventSource` per URL, fans validated envelopes out to all
  subscribers, and closes the underlying connection when the last subscriber
  leaves.
- `src/agentContext.ts` — `useModuleEvents` subscribes through `getSharedStream`,
  Zod-validates each envelope, and **excludes** `ui.intent` (domain events only).
  Same public signature.
- `src/agentDriver.tsx` — `AgentDriverProvider` subscribes through
  `getSharedStream`, keeps only `type === 'ui.intent'`, reads `envelope.payload`
  as `UiIntent`, validates it, dedups by `event_id`, then dispatches. The second
  `EventSource` is removed.
- `src/agentSurface/registry.ts` + `agentSurface/AgentSurface.tsx` — the registry
  push tracks the last-sent snapshot and current `version`; computes an RFC-6902
  patch via `fast-json-patch`; sends a `delta` when a baseline exists, else a
  full `snapshot`; on **409** clears the baseline and resends full.
- `package.json` — add runtime deps `zod` and `fast-json-patch`.

### Python connector (`minder_python_sdk`)

- `connector.py`:
  - Replace the `/events` and `/ui/intents` routes with a single
    `GET /connector/stream` that session-filters enveloped events (domain +
    `ui.intent`). Reuse the existing per-consumer queue + slow-consumer-drop
    behavior.
  - Rework `POST /connector/ui/snapshot` to accept `kind: 'snapshot'|'delta'` with
    `version`/`base_version`; apply the patch or replace; store `{version,
    snapshot}`; return the accepted `version`; **409** on mismatch, **422** on
    malformed body.
  - `push_ui_intent()` continues to envelope intents (already does) and dispatch
    them onto the merged stream with the correct `session_id`.
- Add `jsonpatch` dependency for RFC-6902 apply.
- `ui.py` — `is_intent()` aligns with the enveloped payload shape.
- `minder/core/modules/remote.py` — repoint any `/events` consumer to `/stream`.
  `read_module_context` and `/context` are unchanged.

## Error handling

- Invalid envelope or intent at the SSE boundary → dropped + `console.warn`
  (client); never reaches a form controller.
- Malformed snapshot POST → **422**.
- Delta `base_version` mismatch → **409** → client full resend (self-healing after
  a backend restart or a missed reconnect).
- Slow SSE consumer → existing silent-drop behavior preserved.
- `EventSource` reconnect → dedup by `event_id` prevents double-firing intents;
  the snapshot baseline self-heals via the 409 path.

## Testing

Per `CLAUDE.md`, both unit tests **and** a real end-to-end run with a live API key
are required.

- **Vitest (TS):**
  - Zod schemas accept valid and reject malformed envelopes/intents.
  - Delta computation produces a correct RFC-6902 patch; 409 triggers a full
    resend.
  - Intent dedup by `event_id` drops a replayed intent.
  - `getSharedStream` fans one connection out to multiple subscribers and closes
    the `EventSource` on last unsubscribe.
  - Existing tests updated to the merged `/connector/stream` endpoint.
- **Pytest (Python):**
  - `POST /ui/snapshot` full-then-delta applies correctly; stored snapshot matches.
  - `base_version` mismatch returns 409.
  - `/connector/stream` emits enveloped intents filtered by `session_id`.
  - Intent validation rejects an unknown `intent` kind.
- **End-to-end:** `OPENAI_API_KEY` set; run the real app and exercise the
  agent-drives-UI path (a `fill`/`submit` intent reaching a real form) and the
  surface-read round trip (registry snapshot → `/context` → agent reads it).

## Out of scope (explicitly rejected)

- RxJS Observable agent core — our hook model is simpler and correct for a React
  SDK; adopting RxJS is a large refactor for no real gain.
- Protobuf transport / content negotiation — bandwidth optimization for
  high-volume token streaming we do not do; JSON + SSE is right for periodic
  snapshots.
- A2UI generative UI (agent-authored component trees from a host catalog) —
  interesting future extension of the fixed `DecisionPacket`, but a project of its
  own, not part of this change.
