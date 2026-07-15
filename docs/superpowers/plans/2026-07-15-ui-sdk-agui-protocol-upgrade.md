# minder_ui_sdk ag-ui Protocol Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring four ag-ui-inspired improvements to the shared agent/human UI layer — enveloped events end-to-end, one multiplexed SSE stream, Zod validation at the boundary, and JSON-Patch snapshot deltas — across both the TypeScript `minder_ui_sdk` and the Python `minder_python_sdk` connector.

**Architecture:** A single `GET /connector/stream?session=` SSE endpoint replaces `/connector/events` + `/connector/ui/intents`, carrying all `EventEnvelope`s (domain events + `ui.intent`). The browser consumes it through one ref-counted `EventSource` singleton keyed by URL, validating every envelope with Zod. The `AgentSurface` snapshot POST channel switches to snapshot-once + RFC-6902 deltas with optimistic versioning (409 → full resend). Clean cut: old wire shapes are removed, not kept.

**Tech Stack:** TypeScript + React 18, Vitest, Zod, fast-json-patch (TS); FastAPI, jsonpatch, pytest/TestClient (Python).

## Global Constraints

- SDK line length 100; TS strict; zero-`any` in new code except deliberate `unknown` narrowing.
- Python: line length 100 (Black + Ruff), type hints on public APIs, Google-style docstrings.
- Clean cut — no dual-path back-compat. `/connector/events` and `/connector/ui/intents` are removed.
- The merged stream and the snapshot POST share the same `session` so both the driver and the surface push resolve to one `EventSource` per URL.
- Envelope shape is exactly: `{ event_id, type, module, ts, source, actor?, session_id?, payload }`.
- `ui.intent` envelope payload is exactly `{ intent: <UiIntent>, warning?: string | null }` (already produced by `push_ui_intent`).
- Per `CLAUDE.md`: both unit tests AND a real end-to-end run with `OPENAI_API_KEY` are required before the work is done.
- Run TS tests with `npm test` in `minder_ui_sdk/`; run Python tests with `uv run --no-sync pytest` in `minder_python_sdk/`.

---

### Task 1: Zod schemas + validation module (TS)

**Files:**
- Create: `minder_ui_sdk/src/events.ts`
- Modify: `minder_ui_sdk/package.json` (add `zod`, `fast-json-patch`)
- Test: `minder_ui_sdk/tests/events.test.ts`

**Interfaces:**
- Produces: `UiIntentSchema`, `EventEnvelopeSchema`, `EventActorSchema` (Zod); types `UiIntent`, `EventEnvelope<P>`, `EventActor`; helpers `parseEnvelope(data): EventEnvelope | null`, `parseUiIntent(data): UiIntent | null`; constant `UI_INTENT = 'ui.intent'`.

- [ ] **Step 1: Add dependencies**

Edit `minder_ui_sdk/package.json` — add a `dependencies` block (the file currently has none) before `devDependencies`:

```json
  "dependencies": {
    "zod": "^3.23.8",
    "fast-json-patch": "^3.1.1"
  },
```

Then run: `cd minder_ui_sdk && npm install`
Expected: `zod` and `fast-json-patch` appear in `node_modules`.

- [ ] **Step 2: Write the failing test**

Create `minder_ui_sdk/tests/events.test.ts`:

```ts
import { parseEnvelope, parseUiIntent, UI_INTENT } from '../src/events';

const envelope = {
  event_id: 'e1',
  type: UI_INTENT,
  module: 'catalog',
  ts: '2026-07-15T00:00:00Z',
  source: 'agent',
  session_id: 's1',
  payload: { intent: { intent: 'navigate', route: 'home' } },
};

it('parseEnvelope accepts a well-formed envelope', () => {
  const env = parseEnvelope(envelope);
  expect(env?.event_id).toBe('e1');
  expect(env?.type).toBe(UI_INTENT);
});

it('parseEnvelope rejects a missing required field', () => {
  const { event_id, ...bad } = envelope;
  expect(parseEnvelope(bad)).toBeNull();
});

it('parseUiIntent accepts each intent variant', () => {
  expect(parseUiIntent({ intent: 'fill', form: 'f', values: { a: 1 } })?.intent).toBe('fill');
  expect(parseUiIntent({ intent: 'act', name: 'save' })?.intent).toBe('act');
});

it('parseUiIntent rejects an unknown intent kind', () => {
  expect(parseUiIntent({ intent: 'explode', form: 'f' })).toBeNull();
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd minder_ui_sdk && npx vitest run tests/events.test.ts`
Expected: FAIL — cannot resolve `../src/events`.

- [ ] **Step 4: Write `src/events.ts`**

```ts
import { z } from 'zod';

/** The single event type carrying an agent→UI intent. */
export const UI_INTENT = 'ui.intent';

/** The agent-drives-the-real-UI command union. Payload of a `ui.intent` event. */
export const UiIntentSchema = z.discriminatedUnion('intent', [
  z.object({ intent: z.literal('navigate'), route: z.string() }),
  z.object({
    intent: z.literal('fill'),
    form: z.string(),
    values: z.record(z.unknown()),
    partial: z.boolean().optional(),
  }),
  z.object({ intent: z.literal('focus'), form: z.string().nullable().optional(), field: z.string() }),
  z.object({ intent: z.literal('highlight'), control: z.string() }),
  z.object({
    intent: z.literal('request_confirm'),
    target: z.string(),
    summary: z.string().nullable().optional(),
  }),
  z.object({ intent: z.literal('submit'), form: z.string() }),
  z.object({ intent: z.literal('act'), name: z.string() }),
]);
export type UiIntent = z.infer<typeof UiIntentSchema>;

/** Who acted — distinguishes an agent acting for a user from a human. */
export const EventActorSchema = z.object({
  kind: z.enum(['agent', 'human', 'system']),
  agent_id: z.string().nullable().optional(),
  on_behalf_of: z.string().nullable().optional(),
});
export type EventActor = z.infer<typeof EventActorSchema>;

/** A normalized, timestamped, sourced record of something that happened. */
export const EventEnvelopeSchema = z.object({
  event_id: z.string(),
  type: z.string(),
  module: z.string(),
  ts: z.string(),
  source: z.string(),
  actor: EventActorSchema.nullable().optional(),
  session_id: z.string().nullable().optional(),
  payload: z.unknown(),
});
export type EventEnvelope<P = unknown> = Omit<
  z.infer<typeof EventEnvelopeSchema>,
  'payload'
> & { payload: P };

/** Validate an inbound envelope; return null (caller warns + drops) on failure. */
export function parseEnvelope(data: unknown): EventEnvelope | null {
  const r = EventEnvelopeSchema.safeParse(data);
  return r.success ? (r.data as EventEnvelope) : null;
}

/** Validate a `ui.intent` payload's `intent` object. */
export function parseUiIntent(data: unknown): UiIntent | null {
  const r = UiIntentSchema.safeParse(data);
  return r.success ? r.data : null;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd minder_ui_sdk && npx vitest run tests/events.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add minder_ui_sdk/src/events.ts minder_ui_sdk/tests/events.test.ts minder_ui_sdk/package.json minder_ui_sdk/package-lock.json
git commit -m "feat(ui-sdk): Zod schemas for envelope + UiIntent"
```

---

### Task 2: Shared ref-counted EventSource singleton (TS)

**Files:**
- Create: `minder_ui_sdk/src/stream.ts`
- Test: `minder_ui_sdk/tests/stream.test.ts`

**Interfaces:**
- Consumes: `parseEnvelope`, `EventEnvelope` from `./events`.
- Produces: `getSharedStream(url: string, onEnvelope: (env: EventEnvelope) => void): { close(): void }`; `__resetSharedStreams(): void` (test helper).

- [ ] **Step 1: Write the failing test**

Create `minder_ui_sdk/tests/stream.test.ts`:

```ts
import { getSharedStream, __resetSharedStreams } from '../src/stream';
import { UI_INTENT } from '../src/events';

class FakeES {
  static instances: FakeES[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeES.instances.push(this);
  }
  emit(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) } as MessageEvent);
  }
  close() {
    this.closed = true;
  }
}

const env = (id: string) => ({
  event_id: id,
  type: UI_INTENT,
  module: 'm',
  ts: 't',
  source: 'agent',
  payload: {},
});

beforeEach(() => {
  FakeES.instances = [];
  __resetSharedStreams();
  vi.stubGlobal('EventSource', FakeES as unknown as typeof EventSource);
});
afterEach(() => {
  __resetSharedStreams();
  vi.restoreAllMocks();
});

it('two subscribers to the same URL share one EventSource', () => {
  const a: string[] = [];
  const b: string[] = [];
  getSharedStream('http://m/s', (e) => a.push(e.event_id));
  getSharedStream('http://m/s', (e) => b.push(e.event_id));
  expect(FakeES.instances.length).toBe(1);
  FakeES.instances[0].emit(env('e1'));
  expect(a).toEqual(['e1']);
  expect(b).toEqual(['e1']);
});

it('closes the underlying EventSource only after the last unsubscribe', () => {
  const h1 = getSharedStream('http://m/s', () => {});
  const h2 = getSharedStream('http://m/s', () => {});
  h1.close();
  expect(FakeES.instances[0].closed).toBe(false);
  h2.close();
  expect(FakeES.instances[0].closed).toBe(true);
});

it('drops an invalid envelope without throwing', () => {
  const seen: string[] = [];
  getSharedStream('http://m/s', (e) => seen.push(e.event_id));
  FakeES.instances[0].emit({ nope: true });
  expect(seen).toEqual([]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_ui_sdk && npx vitest run tests/stream.test.ts`
Expected: FAIL — cannot resolve `../src/stream`.

- [ ] **Step 3: Write `src/stream.ts`**

```ts
import { parseEnvelope, type EventEnvelope } from './events';

type Sub = (env: EventEnvelope) => void;

interface Shared {
  es: EventSource;
  subscribers: Set<Sub>;
  refCount: number;
}

const streams = new Map<string, Shared>();

/**
 * Subscribe to a connector SSE stream, sharing one `EventSource` per URL across
 * all callers. Envelopes are JSON-parsed and Zod-validated once; invalid frames
 * are dropped with a warning. The returned handle's `close()` decrements the
 * ref-count and closes the socket when the last subscriber leaves.
 */
export function getSharedStream(url: string, onEnvelope: Sub): { close(): void } {
  let shared = streams.get(url);
  if (!shared) {
    const es = new EventSource(url);
    const s: Shared = { es, subscribers: new Set<Sub>(), refCount: 0 };
    es.onmessage = (e: MessageEvent) => {
      let data: unknown;
      try {
        data = JSON.parse(e.data);
      } catch {
        return;
      }
      const env = parseEnvelope(data);
      if (!env) {
        console.warn('[minder] dropped invalid event envelope');
        return;
      }
      s.subscribers.forEach((fn) => fn(env));
    };
    streams.set(url, s);
    shared = s;
  }
  shared.subscribers.add(onEnvelope);
  shared.refCount += 1;
  return {
    close() {
      const s = streams.get(url);
      if (!s) return;
      s.subscribers.delete(onEnvelope);
      s.refCount -= 1;
      if (s.refCount <= 0) {
        s.es.close();
        streams.delete(url);
      }
    },
  };
}

/** Test helper: force-close and forget every shared stream. */
export function __resetSharedStreams(): void {
  streams.forEach((s) => s.es.close());
  streams.clear();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd minder_ui_sdk && npx vitest run tests/stream.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add minder_ui_sdk/src/stream.ts minder_ui_sdk/tests/stream.test.ts
git commit -m "feat(ui-sdk): ref-counted shared EventSource singleton"
```

---

### Task 3: Merged `/connector/stream` endpoint (Python) + liveness repoint

**Files:**
- Modify: `minder_python_sdk/minder_python_sdk/connector.py` (remove `/connector/events` at 1004-1035, `/connector/ui/intents` at 1037-1061, the `_ui_bus` field at ~187 and its enqueue loop at 472-476; add `/connector/stream`)
- Modify: `minder/core/modules/liveness.py:119` (`/connector/events` → `/connector/stream`)
- Test: `minder_python_sdk/tests/test_connector_ext.py` (add stream tests)

**Interfaces:**
- Produces: `GET /connector/stream?session=<id>` — SSE of `EventEnvelope.to_dict()` frames where `env.session_id in (None, session)`. Emits `: ok` on open and `: ping` heartbeats.
- Consumes: existing `self._event_listeners`, `make_envelope`, `EventEnvelope`.

- [ ] **Step 1: Write the failing test**

Add to `minder_python_sdk/tests/test_connector_ext.py`:

```python
def test_stream_delivers_ui_intent_for_matching_session():
    from minder_python_sdk import Connector
    from fastapi.testclient import TestClient

    conn = Connector("catalog")
    conn.page("home", path="/", label="Home")
    client = TestClient(conn.asgi())

    with client.stream("GET", "/connector/stream?session=s1") as resp:
        lines = resp.iter_lines()
        assert next(lines) == ": ok"           # open marker
        conn.push_ui_intent("s1", {"intent": "navigate", "route": "home"})
        # advance to the data frame (skip blank separators / pings)
        payload = None
        for _ in range(10):
            line = next(lines)
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
                break
        assert payload is not None
        assert payload["type"] == "ui.intent"
        assert payload["session_id"] == "s1"
        assert payload["payload"]["intent"]["route"] == "home"
```

Ensure `import json` is present at the top of the test file (add it if missing).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_python_sdk && uv run --no-sync pytest tests/test_connector_ext.py::test_stream_delivers_ui_intent_for_matching_session -v`
Expected: FAIL — 404 on `/connector/stream`.

- [ ] **Step 3: Remove the old routes and `_ui_bus`**

In `connector.py`:

Delete the `@app.get("/connector/events")` block (lines ~1004-1035) and the `@app.get("/connector/ui/intents")` block (lines ~1037-1061).

Delete the `_ui_bus` field declaration (line ~187 — `self._ui_bus: dict[str, list[Any]] = {}`).

In `push_ui_intent` (lines ~472-476) delete the enqueue loop so the method ends right after `_dispatch(...)`:

```python
        self._dispatch(
            make_envelope(
                self.name,
                "ui.intent",
                {"intent": intent, "warning": err},
                source="agent" if actor and actor.get("kind") == "agent" else "module",
                actor=actor,
                session_id=session_id,
            )
        )
        return {"ok": True, "warning": err}
```

- [ ] **Step 4: Add the merged `/connector/stream` route**

Insert where `/connector/events` used to be:

```python
        @app.get("/connector/stream")
        def stream(request: Request) -> StreamingResponse:
            """One SSE stream of every envelope for a session — module domain
            events and ``ui.intent`` alike. Replaces ``/connector/events`` and
            ``/connector/ui/intents``. Broadcast events (no ``session_id``) reach
            every subscriber; session-scoped events reach only their session."""
            import queue as _queue

            session = request.query_params.get("session") or "default"
            q: "_queue.Queue[EventEnvelope]" = _queue.Queue(maxsize=256)

            def listener(env: EventEnvelope) -> None:
                if env.session_id not in (None, session):
                    return
                try:
                    q.put_nowait(env)
                except _queue.Full:  # slow consumer — drop rather than block
                    pass

            self._event_listeners.append(listener)

            def gen() -> Iterator[bytes]:
                try:
                    yield b": ok\n\n"
                    while True:
                        try:
                            env = q.get(timeout=15)
                            yield f"data: {json.dumps(env.to_dict())}\n\n".encode()
                        except _queue.Empty:
                            yield b": ping\n\n"
                finally:
                    try:
                        self._event_listeners.remove(listener)
                    except ValueError:
                        pass

            return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 5: Repoint liveness**

In `minder/core/modules/liveness.py`, change line ~119:

```python
        events_url = f"{url.rstrip('/')}/connector/stream"
```

Update the surrounding docstring/comment references from `/connector/events` to `/connector/stream` in `liveness.py` (lines ~3, ~118), `registry.py` (~227), and `minder/web/server.py` (~137).

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd minder_python_sdk && uv run --no-sync pytest tests/test_connector_ext.py tests/test_ui_surface.py -v`
Expected: PASS — new stream test green; fix any existing test that referenced the removed `/connector/events` or `/connector/ui/intents` by pointing it at `/connector/stream`.

- [ ] **Step 7: Commit**

```bash
git add minder_python_sdk/minder_python_sdk/connector.py minder_python_sdk/tests/test_connector_ext.py minder/core/modules/liveness.py minder/core/modules/registry.py minder/web/server.py
git commit -m "feat(connector): merge SSE into /connector/stream; repoint liveness"
```

---

### Task 4: agentDriver consumes the merged stream (TS)

**Files:**
- Modify: `minder_ui_sdk/src/agentDriver.tsx` (replace the raw `EventSource` block; import types from `./events`)
- Modify: `minder_ui_sdk/tests/agentDriver.test.tsx` (envelopes + new URL)

**Interfaces:**
- Consumes: `getSharedStream` from `./stream`; `UiIntent`, `parseUiIntent`, `UI_INTENT`, `EventEnvelope` from `./events`.
- Produces: unchanged public exports (`AgentDriverProvider`, `useAgentForm`, `useAgentHighlight`, `useAgentActivity`, type `UiIntent` re-exported).

- [ ] **Step 1: Update the test (new envelope wire + URL)**

Replace the `FakeES` class and the first two `it(...)` in `tests/agentDriver.test.tsx`:

```ts
import { UI_INTENT } from '../src/events';
import { __resetSharedStreams } from '../src/stream';

let __seq = 0;
class FakeES {
  static last: FakeES | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeES.last = this;
  }
  emit(intent: UiIntent, eventId?: string) {
    const env = {
      event_id: eventId ?? `e${(__seq += 1)}`,
      type: UI_INTENT,
      module: 'catalog',
      ts: 't',
      source: 'agent',
      session_id: 's1',
      payload: { intent },
    };
    this.onmessage?.({ data: JSON.stringify(env) } as MessageEvent);
  }
  close() {
    this.closed = true;
  }
}

afterEach(() => __resetSharedStreams());
```

Update the URL assertion:

```ts
it('subscribes to the merged session stream', () => {
  const { es } = setup();
  expect(es.url).toBe('http://m/connector/stream?session=s1');
});
```

Add a dedup test at the end of the file:

```ts
it('ignores a replayed intent with the same event_id', () => {
  const { es, navSpy } = setup();
  act(() => es.emit({ intent: 'navigate', route: 'home' }, 'dup'));
  act(() => es.emit({ intent: 'navigate', route: 'home' }, 'dup'));
  expect(navSpy).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_ui_sdk && npx vitest run tests/agentDriver.test.tsx`
Expected: FAIL — URL is still `/connector/ui/intents?...` and no dedup.

- [ ] **Step 3: Rewrite the subscription in `agentDriver.tsx`**

At the top, replace the local `UiIntent` type declaration with an import and re-export:

```ts
import { getSharedStream } from './stream';
import { UI_INTENT, parseUiIntent, type UiIntent, type EventEnvelope } from './events';
export type { UiIntent };
```

Delete the inline `export type UiIntent = ...` union (lines ~21-28).

Change the default `path` in `AgentDriverProviderProps` and its usage from `/connector/ui/intents` to `/connector/stream`:

```ts
  /** SSE path relative to `apiBase`. Defaults to `/connector/stream`. */
  path?: string;
```
```ts
  path = '/connector/stream',
```

Replace the `useEffect` that opens the `EventSource` (lines ~94-111) with:

```ts
  useEffect(() => {
    if (!apiBase || typeof EventSource === 'undefined') return;
    const qs = sessionId ? `?session=${encodeURIComponent(sessionId)}` : '';
    const url = `${apiBase.replace(/\/$/, '')}${path}${qs}`;
    const seen = new Set<string>();
    const order: string[] = [];
    const handle = getSharedStream(url, (env: EventEnvelope) => {
      if (env.type !== UI_INTENT) return;
      if (seen.has(env.event_id)) return; // drop replays after a reconnect
      seen.add(env.event_id);
      order.push(env.event_id);
      if (order.length > 512) seen.delete(order.shift() as string);
      const payload = env.payload as { intent?: unknown } | null;
      const intent = parseUiIntent(payload?.intent);
      if (!intent) {
        console.warn('[minder] dropped invalid ui.intent payload');
        return;
      }
      dispatchIntent(intent, forms.current, onNavigateRef.current, setHighlighted);
      onIntentRef.current?.(intent);
      tick.current += 1;
      setActivity({ intent, tick: tick.current });
    });
    return () => handle.close();
  }, [apiBase, sessionId, path]);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd minder_ui_sdk && npx vitest run tests/agentDriver.test.tsx`
Expected: PASS (all existing + the new dedup test).

- [ ] **Step 5: Commit**

```bash
git add minder_ui_sdk/src/agentDriver.tsx minder_ui_sdk/tests/agentDriver.test.tsx
git commit -m "feat(ui-sdk): drive UI from merged stream with envelope dedup"
```

---

### Task 5: agentContext consumes the merged stream (TS)

**Files:**
- Modify: `minder_ui_sdk/src/agentContext.ts` (import envelope types from `./events`; subscribe via `getSharedStream`; exclude `ui.intent`)
- Modify: `minder_ui_sdk/src/index.ts` (re-export envelope types from `./events` if their source moved)
- Test: `minder_ui_sdk/tests/agentContext.test.tsx` (envelopes + merged URL)

**Interfaces:**
- Consumes: `getSharedStream` from `./stream`; `EventEnvelope`, `EventActor`, `UI_INTENT` from `./events`.
- Produces: unchanged `useModuleEvents`, `useAgentContext`; `UseModuleEventsOptions` gains `sessionId?: string`.

- [ ] **Step 1: Write/adjust the failing test**

In `minder_ui_sdk/tests/agentContext.test.tsx`, ensure the fake EventSource emits **envelopes** and assert the merged URL. Replace the emit + URL assertions:

```ts
import { UI_INTENT } from '../src/events';
import { __resetSharedStreams } from '../src/stream';

// inside FakeES:
emitEnvelope(type: string, payload: unknown, sessionId = 's1') {
  const env = {
    event_id: `e${Math.random()}`,
    type,
    module: 'catalog',
    ts: 't',
    source: 'module',
    session_id: sessionId,
    payload,
  };
  this.onmessage?.({ data: JSON.stringify(env) } as MessageEvent);
}

afterEach(() => __resetSharedStreams());

it('subscribes to the merged stream and buffers domain events', () => {
  // render useModuleEvents('http://m', { sessionId: 's1', types: ['queue.changed'] })
  // expect FakeES.last.url === 'http://m/connector/stream?session=s1'
  // after emitEnvelope('queue.changed', { n: 3 }) the hook exposes one event
  // after emitEnvelope(UI_INTENT, { intent: { intent: 'navigate', route: 'x' } })
  //   the hook still exposes only the domain event (ui.intent excluded)
});
```

Fill in the render + assertions following the existing `agentContext.test.tsx` structure (use a small harness component that renders `events.length` and the last `type`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_ui_sdk && npx vitest run tests/agentContext.test.tsx`
Expected: FAIL — URL still `/connector/events`, ui.intent not excluded.

- [ ] **Step 3: Rewrite `agentContext.ts`**

Replace the local `EventActor` and `EventEnvelope` interface declarations (lines ~11-27) with imports + re-exports:

```ts
import { getSharedStream } from './stream';
import { UI_INTENT, type EventEnvelope, type EventActor } from './events';
export type { EventEnvelope, EventActor };
```

Add `sessionId` to the options type:

```ts
export interface UseModuleEventsOptions {
  /** Session whose stream to join; shares the driver's EventSource when equal. */
  sessionId?: string;
  /** SSE path relative to `apiBase`. Defaults to `/connector/stream`. */
  path?: string;
  limit?: number;
  types?: string[];
  onEvent?: (env: EventEnvelope) => void;
}
```

Replace the `useEffect`/`EventSource` block in `useModuleEvents` (lines ~64-93) with:

```ts
  const { sessionId, path = '/connector/stream', limit = 100, types, onEvent } = opts;
  // ...existing useState/useRef unchanged...
  const typeKey = types ? types.join(',') : '';
  useEffect(() => {
    if (!apiBase || typeof EventSource === 'undefined') return;
    const qs = sessionId ? `?session=${encodeURIComponent(sessionId)}` : '';
    const url = `${apiBase.replace(/\/$/, '')}${path}${qs}`;
    const handle = getSharedStream(url, (env) => {
      if (env.type === UI_INTENT) return; // the driver owns intents
      if (types && !types.includes(env.type)) return;
      onEventRef.current?.(env);
      setEvents((prev) => {
        const next = [...prev, env];
        return next.length > limit ? next.slice(next.length - limit) : next;
      });
    });
    return () => handle.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, path, limit, typeKey, sessionId]);
```

The `connected` flag: `getSharedStream` does not expose open/error. Drop the `connected` state and its return, OR keep it always-true. To preserve the return shape, return `connected: true` (the shared `EventSource` auto-reconnects; a per-consumer connected flag is no longer meaningful). Update the return type/JSDoc accordingly.

- [ ] **Step 4: Update `index.ts` exports**

Confirm `src/index.ts` still exports `EventEnvelope`, `EventActor` — they now originate in `events.ts` and are re-exported through `agentContext.ts`, so the existing `export type { EventEnvelope, EventActor, ... } from './agentContext'` line keeps working. Add an export for the new public API:

```ts
export { UI_INTENT, parseEnvelope, parseUiIntent } from './events';
export { getSharedStream } from './stream';
```

- [ ] **Step 5: Run the full TS suite**

Run: `cd minder_ui_sdk && npm test`
Expected: PASS — all files including `agentContext.test.tsx`.

- [ ] **Step 6: Commit**

```bash
git add minder_ui_sdk/src/agentContext.ts minder_ui_sdk/src/index.ts minder_ui_sdk/tests/agentContext.test.tsx
git commit -m "feat(ui-sdk): read module events from merged stream, exclude intents"
```

---

### Task 6: Snapshot delta + versioning (Python)

**Files:**
- Modify: `minder_python_sdk/minder_python_sdk/connector.py` (`/connector/ui/snapshot` at 1076-1083; add `self._ui_snapshot_versions` beside `_ui_snapshots`)
- Modify: `minder_python_sdk/pyproject.toml` (add `jsonpatch`)
- Test: `minder_python_sdk/tests/test_connector_ext.py`

**Interfaces:**
- Produces: `POST /connector/ui/snapshot` accepts `{session_id, kind: 'snapshot', snapshot}` → `{ok, version}`; `{session_id, kind: 'delta', base_version, delta}` → `{ok, version}` or 409 `{ok:false, error:'version_mismatch', version}`; unknown kind → 422. `GET /connector/context` still returns the full merged `ui_snapshot`.

- [ ] **Step 1: Add the dependency**

In `minder_python_sdk/pyproject.toml` `dependencies` list, add:

```toml
    "jsonpatch>=1.33",
```

Run: `cd minder_python_sdk && uv sync` (or `uv pip install jsonpatch`).

- [ ] **Step 2: Write the failing test**

Add to `tests/test_connector_ext.py`:

```python
def test_snapshot_then_delta_applies_and_versions():
    from minder_python_sdk import Connector
    from fastapi.testclient import TestClient

    conn = Connector("catalog")
    client = TestClient(conn.asgi())

    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "s1", "kind": "snapshot", "snapshot": {"page": "home", "n": 1}},
    )
    assert r.json() == {"ok": True, "version": 1}

    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "s1", "kind": "delta", "base_version": 1,
              "delta": [{"op": "replace", "path": "/n", "value": 2}]},
    )
    assert r.json() == {"ok": True, "version": 2}

    ctx = client.get("/connector/context", headers={"X-Minder-Session": "s1"}).json()
    assert ctx["ui_snapshot"] == {"page": "home", "n": 2}


def test_snapshot_delta_version_mismatch_returns_409():
    from minder_python_sdk import Connector
    from fastapi.testclient import TestClient

    conn = Connector("catalog")
    client = TestClient(conn.asgi())
    client.post("/connector/ui/snapshot",
                json={"session_id": "s1", "kind": "snapshot", "snapshot": {"n": 1}})
    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "s1", "kind": "delta", "base_version": 99,
              "delta": [{"op": "replace", "path": "/n", "value": 2}]},
    )
    assert r.status_code == 409
    assert r.json()["version"] == 1
```

Confirm the session header name matches `_session_from_headers` (inspect it; the test above assumes `X-Minder-Session` — adjust the header key to whatever that helper reads).

- [ ] **Step 3: Run test to verify it fails**

Run: `cd minder_python_sdk && uv run --no-sync pytest tests/test_connector_ext.py -k snapshot -v`
Expected: FAIL — current route ignores `kind`, returns `{"ok": True}` with no version.

- [ ] **Step 4: Implement versioned snapshot/delta**

Add the version map near the `_ui_snapshots` field (line ~190):

```python
        self._ui_snapshot_versions: dict[str, int] = {}
```

Ensure `JSONResponse` is imported at the top of `connector.py`:

```python
from starlette.responses import JSONResponse
```

Replace the `/connector/ui/snapshot` route body:

```python
        @app.post("/connector/ui/snapshot")
        async def ui_snapshot(request: Request) -> Any:
            """Store the frontend's declarative UI snapshot for one session so the
            agent can read what's on screen via ``/connector/context``. First push
            is a full ``snapshot``; later pushes are RFC-6902 ``delta``s guarded by
            an optimistic ``base_version`` (mismatch → 409, client resends full)."""
            body = await _json_body(request)
            session = body.get("session_id") or "default"
            kind = body.get("kind") or "snapshot"
            if kind == "snapshot":
                self._ui_snapshots[session] = body.get("snapshot") or {}
                ver = self._ui_snapshot_versions.get(session, 0) + 1
                self._ui_snapshot_versions[session] = ver
                return {"ok": True, "version": ver}
            if kind == "delta":
                cur = self._ui_snapshot_versions.get(session, 0)
                if body.get("base_version") != cur:
                    return JSONResponse(
                        {"ok": False, "error": "version_mismatch", "version": cur},
                        status_code=409,
                    )
                import jsonpatch

                patched = jsonpatch.apply_patch(
                    self._ui_snapshots.get(session, {}), body.get("delta") or []
                )
                self._ui_snapshots[session] = patched
                ver = cur + 1
                self._ui_snapshot_versions[session] = ver
                return {"ok": True, "version": ver}
            return JSONResponse({"ok": False, "error": "bad_kind"}, status_code=422)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd minder_python_sdk && uv run --no-sync pytest tests/test_connector_ext.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add minder_python_sdk/minder_python_sdk/connector.py minder_python_sdk/pyproject.toml minder_python_sdk/tests/test_connector_ext.py
git commit -m "feat(connector): versioned snapshot + RFC-6902 delta on /ui/snapshot"
```

---

### Task 7: Snapshot delta client (TS)

**Files:**
- Modify: `minder_ui_sdk/src/agentSurface/AgentSurface.tsx` (the push effect in `AgentRegistryProvider`, lines ~43-64)
- Test: `minder_ui_sdk/tests/agentSurfaceSnapshot.test.tsx`

**Interfaces:**
- Consumes: `compare` from `fast-json-patch`; `reg.snapshot(): UiSnapshot` (unchanged).
- Produces: POST body `{session_id, kind:'snapshot', snapshot}` on first/reset push, `{session_id, kind:'delta', base_version, delta}` after; handles 409 by resending full.

- [ ] **Step 1: Update the test**

Rewrite `tests/agentSurfaceSnapshot.test.tsx`'s fetch mock to return a JSON version, keep the first-push assertion, and add a delta assertion:

```ts
let __ver = 0;
beforeEach(() => {
  vi.useFakeTimers();
  __ver = 0;
  (globalThis as any).fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ version: (__ver += 1) }) }),
  );
});
```

Keep the existing assertions but add `expect(body.kind).toBe('snapshot')` to the first-push test. Add a second test:

```ts
it('sends a delta after the first full snapshot', async () => {
  const view = render(/* AgentRegistryProvider with a stateful Agent.Data value */);
  await act(async () => { vi.advanceTimersByTime(200); await Promise.resolve(); });
  // trigger a data change (re-render Agent.Data with a new value), then:
  await act(async () => { vi.advanceTimersByTime(200); await Promise.resolve(); });
  const fetchMock = (globalThis as any).fetch as ReturnType<typeof vi.fn>;
  const last = JSON.parse(fetchMock.mock.calls.at(-1)![1].body);
  expect(last.kind).toBe('delta');
  expect(last.base_version).toBe(1);
  expect(Array.isArray(last.delta)).toBe(true);
});
```

Use a small wrapper component with `useState` so a button click changes an `Agent.Data` value between the two timer advances.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_ui_sdk && npx vitest run tests/agentSurfaceSnapshot.test.tsx`
Expected: FAIL — body has no `kind`/`delta`; mock lacks `.json`.

- [ ] **Step 3: Rewrite the push effect in `AgentSurface.tsx`**

Add the import:

```ts
import { compare } from 'fast-json-patch';
import type { UiSnapshot } from './registry';
```

Replace the push `useEffect` (lines ~43-64) with a versioned snapshot/delta push:

```ts
  useEffect(() => {
    if (!apiBase) return;
    const base = apiBase.replace(/\/$/, '');
    const url = `${base}/connector/ui/snapshot`;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let baseline: UiSnapshot | null = null;
    let version = 0;

    const postFull = async (snap: UiSnapshot): Promise<void> => {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, kind: 'snapshot', snapshot: snap }),
      });
      const j = (await res.json()) as { version: number };
      version = j.version;
      baseline = snap;
    };

    const push = async (): Promise<void> => {
      const snap = reg.snapshot();
      try {
        if (!baseline) {
          await postFull(snap);
          return;
        }
        const delta = compare(baseline as object, snap as object);
        if (delta.length === 0) return;
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, kind: 'delta', base_version: version, delta }),
        });
        if (res.status === 409) {
          baseline = null;
          await postFull(snap);
          return;
        }
        const j = (await res.json()) as { version: number };
        version = j.version;
        baseline = snap;
      } catch {
        /* best-effort — a dropped snapshot self-heals on the next push */
      }
    };

    const schedule = (): void => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => void push(), 150);
    };
    const unsub = reg.subscribe(schedule);
    schedule();
    return () => {
      if (timer) clearTimeout(timer);
      unsub();
    };
  }, [apiBase, sessionId, reg]);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd minder_ui_sdk && npx vitest run tests/agentSurfaceSnapshot.test.tsx`
Expected: PASS (first-push snapshot + delta).

- [ ] **Step 5: Run the full TS suite**

Run: `cd minder_ui_sdk && npm test`
Expected: PASS — every test file.

- [ ] **Step 6: Commit**

```bash
git add minder_ui_sdk/src/agentSurface/AgentSurface.tsx minder_ui_sdk/tests/agentSurfaceSnapshot.test.tsx
git commit -m "feat(ui-sdk): push snapshot once then JSON-Patch deltas with 409 resync"
```

---

### Task 8: End-to-end verification (real app)

**Files:** none (verification only).

**Interfaces:** exercises the full wire — merged stream, enveloped intents, delta snapshots — through the running app.

- [ ] **Step 1: Run the complete unit suites**

```bash
cd minder_ui_sdk && npm test
cd ../minder_python_sdk && uv run --no-sync pytest -q
```
Expected: both green.

- [ ] **Step 2: Type/lint gates**

```bash
cd minder_python_sdk && uv run --no-sync ruff check . && uv run --no-sync mypy minder_python_sdk
cd ../minder_ui_sdk && npx tsc --noEmit
```
Expected: no errors. Fix any surfaced by the moved types.

- [ ] **Step 3: Rebuild the committed web bundle (deploy footgun)**

If `minder_ui_sdk` is consumed by `web-ui`, rebuild the frontend so `minder/web/static/` reflects the new wire:

```bash
make build-ui
```
Expected: build succeeds; `minder/web/static/` updated.

- [ ] **Step 4: Real end-to-end run (per CLAUDE.md)**

```bash
export OPENAI_API_KEY="…"
make run
```
Then, with a module that uses the SDK mounted:
- Confirm a single `EventSource` to `/connector/stream?session=…` in the browser network tab (not two).
- Trigger an agent `fill`/`submit` intent and confirm the real form updates and the intent is not double-applied.
- Change on-screen data and confirm the snapshot POSTs show one `kind:"snapshot"` then `kind:"delta"` bodies, and that the agent's `read_module_context` / `GET /connector/context` returns the merged current snapshot.

- [ ] **Step 5: Commit the rebuilt bundle (if changed)**

```bash
git add minder/web/static
git commit -m "build(web): rebuild static bundle for merged-stream UI SDK"
```

---

## Self-Review

**Spec coverage:**
- #1 delta snapshots → Tasks 6 (backend) + 7 (client). ✅
- #2 enveloped intents → Tasks 1 (schema) + 3 (backend already envelopes; `_ui_bus` dropped) + 4 (client reads `payload.intent`, dedups by `event_id`). ✅
- #3 Zod validation → Tasks 1 (schemas) + 2/4/5 (boundary `parseEnvelope`/`parseUiIntent`). ✅
- #4 one multiplexed stream → Tasks 2 (shared EventSource) + 3 (`/connector/stream`) + 4/5 (both consumers share the URL). ✅
- Clean-cut removal of old endpoints + liveness repoint → Task 3. ✅
- Deps (`zod`, `fast-json-patch`, `jsonpatch`) → Tasks 1, 6. ✅
- Real e2e per CLAUDE.md → Task 8. ✅

**Type consistency:** `getSharedStream(url, onEnvelope)` signature identical in Tasks 2/4/5. `EventEnvelope`/`UiIntent`/`EventActor` sourced once in `events.ts`, re-exported from `agentDriver.tsx` and `agentContext.ts`. Snapshot POST shape identical across Tasks 6/7 (`kind`, `base_version`/`version`, `delta`, `snapshot`). `parseUiIntent` reads `payload.intent` matching the backend's `{"intent": intent, "warning": err}` payload.

**Open verification during execution:** the exact session-header key used by `_session_from_headers` (Task 6 Step 2) and whether `agentContext.test.tsx` already stubs `EventSource` (Task 5) must be confirmed against the real files, not assumed.
