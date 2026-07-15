# Agent Declarative UI Wrapper (`Agent.*`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a declarative `Agent.Page` / `Agent.Data` / `Agent.Button` wrapper layer to `minder_ui_sdk` so an agent can read what's on screen and trigger wrapped actions, reusing the existing SSE intent/event transport.

**Architecture:** A pure browser-side registry collects `{page, data, actions}` from transparent wrapper components. An `AgentRegistryProvider` pushes a debounced snapshot to a new `POST /connector/ui/snapshot` endpoint (read path, folded into `GET /connector/context`) and, when the existing `AgentDriverProvider` delivers a new `{intent:'act', name}` intent, runs the matching action's `onAct` immediately (act path). No new transport — only one new intent variant and one snapshot endpoint.

**Tech Stack:** TypeScript + React 18 (source-only SDK, Vitest + jsdom + @testing-library/react); Python FastAPI connector in `minder_python_sdk` (pytest + `fastapi.testclient.TestClient`).

## Global Constraints

- SDK is **source-only, no build step**; modules consume `minder_ui_sdk/src/*` via Vite alias. Peer dep `react@^18.3.1`.
- Line length 100 (Black + Ruff) for Python; Google-style docstrings; mypy-strict typing on public Python APIs.
- Wrappers are **transparent**: they register + render `children` verbatim, no layout/styling.
- `Agent.Button.onAct` **runs immediately** — no approval gate.
- Action/data names are **scoped by the enclosing `Agent.Page`**: `${page}.${name}`.
- Each `Agent.Data` value is capped at **32768 characters** serialized; over-cap values are truncated with `truncated: true`.
- Reuse existing transport: act via `POST /connector/ui/intent` → `push_ui_intent` → `/connector/ui/intents` SSE; read via connector snapshot cache surfaced in `/connector/context`.
- SDK test command: `cd minder_ui_sdk && npm run test` (`vitest run`). Backend: `cd minder_python_sdk && python -m pytest tests/ -q`.
- Commits: no `Co-Authored-By: Claude` trailer.

---

### Task 1: Registry core (pure, no React)

**Files:**
- Create: `minder_ui_sdk/src/agentSurface/registry.ts`
- Test: `minder_ui_sdk/tests/registry.test.ts`

**Interfaces:**
- Produces:
  - `interface DataEntry { name: string; description?: string; value: unknown }`
  - `interface ActionEntry { name: string; description?: string; onAct: () => void | Promise<void> }`
  - `interface UiSnapshot { page: string | null; data: { name: string; description?: string; value: unknown; truncated?: boolean }[]; actions: { name: string; description?: string }[] }`
  - `createRegistry(): Registry` with methods `setPage(name: string | null)`, `getPage(): string | null`, `setData(e: DataEntry)`, `removeData(name: string)`, `setAction(e: ActionEntry)`, `removeAction(name: string)`, `run(name: string): boolean`, `snapshot(): UiSnapshot`, `subscribe(fn: () => void): () => void`
  - `MAX_VALUE_CHARS = 32768`

- [ ] **Step 1: Write the failing test**

```ts
// minder_ui_sdk/tests/registry.test.ts
import { describe, it, expect, vi } from 'vitest';
import { createRegistry, MAX_VALUE_CHARS } from '../src/agentSurface/registry';

describe('registry', () => {
  it('snapshots page, data and actions', () => {
    const r = createRegistry();
    r.setPage('products');
    r.setData({ name: 'products.list', description: 'rows', value: [{ id: 1 }] });
    r.setAction({ name: 'products.add', description: 'add', onAct: () => {} });
    const s = r.snapshot();
    expect(s.page).toBe('products');
    expect(s.data).toEqual([{ name: 'products.list', description: 'rows', value: [{ id: 1 }] }]);
    expect(s.actions).toEqual([{ name: 'products.add', description: 'add' }]);
  });

  it('run() invokes the matching action and returns true; unknown returns false', () => {
    const r = createRegistry();
    const spy = vi.fn();
    r.setAction({ name: 'a', onAct: spy });
    expect(r.run('a')).toBe(true);
    expect(spy).toHaveBeenCalledOnce();
    expect(r.run('missing')).toBe(false);
  });

  it('removeData / removeAction drop entries from the snapshot', () => {
    const r = createRegistry();
    r.setData({ name: 'd', value: 1 });
    r.removeData('d');
    expect(r.snapshot().data).toEqual([]);
  });

  it('caps oversized values and flags truncated', () => {
    const r = createRegistry();
    const big = 'x'.repeat(MAX_VALUE_CHARS + 10);
    r.setData({ name: 'd', value: big });
    const entry = r.snapshot().data[0];
    expect(entry.truncated).toBe(true);
    expect((entry.value as string).length).toBe(MAX_VALUE_CHARS);
  });

  it('subscribe fires on mutation and unsubscribe stops it', () => {
    const r = createRegistry();
    const fn = vi.fn();
    const off = r.subscribe(fn);
    r.setPage('p');
    expect(fn).toHaveBeenCalledOnce();
    off();
    r.setPage('q');
    expect(fn).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_ui_sdk && npx vitest run tests/registry.test.ts`
Expected: FAIL — `Cannot find module '../src/agentSurface/registry'`

- [ ] **Step 3: Write minimal implementation**

```ts
// minder_ui_sdk/src/agentSurface/registry.ts
export const MAX_VALUE_CHARS = 32768;

export interface DataEntry {
  name: string;
  description?: string;
  value: unknown;
}

export interface ActionEntry {
  name: string;
  description?: string;
  onAct: () => void | Promise<void>;
}

export interface SnapshotDataEntry {
  name: string;
  description?: string;
  value: unknown;
  truncated?: boolean;
}

export interface UiSnapshot {
  page: string | null;
  data: SnapshotDataEntry[];
  actions: { name: string; description?: string }[];
}

export interface Registry {
  setPage(name: string | null): void;
  getPage(): string | null;
  setData(entry: DataEntry): void;
  removeData(name: string): void;
  setAction(entry: ActionEntry): void;
  removeAction(name: string): void;
  run(name: string): boolean;
  snapshot(): UiSnapshot;
  subscribe(fn: () => void): () => void;
}

function capValue(d: DataEntry): SnapshotDataEntry {
  let serialized: string;
  try {
    serialized = JSON.stringify(d.value) ?? '';
  } catch {
    serialized = String(d.value);
  }
  if (serialized.length > MAX_VALUE_CHARS) {
    return {
      name: d.name,
      description: d.description,
      value: serialized.slice(0, MAX_VALUE_CHARS),
      truncated: true,
    };
  }
  return { name: d.name, description: d.description, value: d.value };
}

export function createRegistry(): Registry {
  let page: string | null = null;
  const data = new Map<string, DataEntry>();
  const actions = new Map<string, ActionEntry>();
  const listeners = new Set<() => void>();
  const emit = (): void => {
    listeners.forEach((l) => l());
  };

  return {
    setPage(name) {
      page = name;
      emit();
    },
    getPage() {
      return page;
    },
    setData(entry) {
      data.set(entry.name, entry);
      emit();
    },
    removeData(name) {
      if (data.delete(name)) emit();
    },
    setAction(entry) {
      actions.set(entry.name, entry);
      emit();
    },
    removeAction(name) {
      if (actions.delete(name)) emit();
    },
    run(name) {
      const a = actions.get(name);
      if (!a) {
        console.warn(`[agent] act on unknown action: ${name}`);
        return false;
      }
      try {
        void a.onAct();
      } catch (e) {
        console.error(`[agent] onAct failed: ${name}`, e);
      }
      return true;
    },
    snapshot() {
      return {
        page,
        data: [...data.values()].map(capValue),
        actions: [...actions.values()].map((a) => ({ name: a.name, description: a.description })),
      };
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd minder_ui_sdk && npx vitest run tests/registry.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add minder_ui_sdk/src/agentSurface/registry.ts minder_ui_sdk/tests/registry.test.ts
git commit -m "feat(sdk): add agent UI registry core with value cap"
```

---

### Task 2: `act` intent variant + wrapper components + provider

**Files:**
- Modify: `minder_ui_sdk/src/agentDriver.tsx` (extend `UiIntent` union, ~lines 21-27)
- Create: `minder_ui_sdk/src/agentSurface/AgentSurface.tsx`
- Modify: `minder_ui_sdk/src/index.ts` (add exports)
- Test: `minder_ui_sdk/tests/agentSurface.test.tsx`

**Interfaces:**
- Consumes: `createRegistry`, `Registry`, `UiSnapshot` from Task 1; `useAgentActivity()` from `../agentDriver` (returns `{ intent: UiIntent; tick: number } | null`).
- Produces:
  - `UiIntent` gains `| { intent: 'act'; name: string }`
  - `AgentRegistryProvider(props: { apiBase?: string; sessionId?: string; children: ReactNode })`
  - `Agent` namespace object: `Agent.Page`, `Agent.Data`, `Agent.Button`
  - `Agent.Page` props `{ name: string; description?: string; children }`
  - `Agent.Data` props `{ name: string; description?: string; value: unknown; children }`
  - `Agent.Button` props `{ name: string; description?: string; onAct: () => void | Promise<void>; children }`

- [ ] **Step 1: Extend the `UiIntent` union**

In `minder_ui_sdk/src/agentDriver.tsx`, change the union (currently lines 21-27) to add the `act` variant as the last member:

```ts
export type UiIntent =
  | { intent: 'navigate'; route: string }
  | { intent: 'fill'; form: string; values: Record<string, unknown>; partial?: boolean }
  | { intent: 'focus'; form?: string | null; field: string }
  | { intent: 'highlight'; control: string }
  | { intent: 'request_confirm'; target: string; summary?: string | null }
  | { intent: 'submit'; form: string }
  | { intent: 'act'; name: string };
```

Confirm `dispatchIntent` (agentDriver.tsx ~line 119) has a default/no-op branch so an `act` intent doesn't throw there — it is consumed by the registry via `useAgentActivity`, not by `dispatchIntent`. If `dispatchIntent` uses a `switch (intent.intent)` with no `default`, leave it (unmatched cases fall through harmlessly); do NOT add form handling for `act`.

- [ ] **Step 2: Write the failing test**

```tsx
// minder_ui_sdk/tests/agentSurface.test.tsx
import { render, screen, act } from '@testing-library/react';
import { AgentDriverProvider, type UiIntent } from '../src/agentDriver';
import { AgentRegistryProvider, Agent } from '../src/agentSurface/AgentSurface';

class FakeES {
  static last: FakeES | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeES.last = this;
  }
  emit(intent: UiIntent) {
    this.onmessage?.({ data: JSON.stringify(intent) } as MessageEvent);
  }
  close() {}
}

function Demo({ onAdd }: { onAdd: () => void }) {
  return (
    <AgentDriverProvider apiBase="http://m" sessionId="s1">
      <AgentRegistryProvider sessionId="s1">
        <Agent.Page name="products" description="Kho">
          <Agent.Data name="list" description="rows" value={[{ id: 1 }]}>
            <div>table</div>
          </Agent.Data>
          <Agent.Button name="add" description="add product" onAct={onAdd}>
            <button>Add</button>
          </Agent.Button>
        </Agent.Page>
      </AgentRegistryProvider>
    </AgentDriverProvider>
  );
}

beforeEach(() => {
  (globalThis as any).EventSource = FakeES as unknown as typeof EventSource;
  (globalThis as any).fetch = vi.fn(() => Promise.resolve({ ok: true }));
});

it('renders children transparently and tags the button control', () => {
  render(<Demo onAdd={() => {}} />);
  expect(screen.getByText('table')).toBeTruthy();
  const btn = screen.getByText('Add');
  expect(btn.closest('[data-agent-control="products.add"]')).toBeTruthy();
});

it('an act intent runs the scoped action', () => {
  const onAdd = vi.fn();
  render(<Demo onAdd={onAdd} />);
  act(() => FakeES.last!.emit({ intent: 'act', name: 'products.add' }));
  expect(onAdd).toHaveBeenCalledOnce();
});

it('act on an unknown name does not throw and does not call onAct', () => {
  const onAdd = vi.fn();
  render(<Demo onAdd={onAdd} />);
  act(() => FakeES.last!.emit({ intent: 'act', name: 'products.nope' }));
  expect(onAdd).not.toHaveBeenCalled();
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd minder_ui_sdk && npx vitest run tests/agentSurface.test.tsx`
Expected: FAIL — `Cannot find module '../src/agentSurface/AgentSurface'`

- [ ] **Step 4: Write the provider and wrappers**

```tsx
// minder_ui_sdk/src/agentSurface/AgentSurface.tsx
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactElement,
  type ReactNode,
} from 'react';
import { useAgentActivity } from '../agentDriver';
import { createRegistry, type Registry } from './registry';

const RegistryCtx = createContext<Registry | null>(null);
const PageCtx = createContext<string | null>(null);

function scoped(page: string | null, name: string): string {
  return page ? `${page}.${name}` : name;
}

export interface AgentRegistryProviderProps {
  apiBase?: string;
  sessionId?: string;
  children: ReactNode;
}

export function AgentRegistryProvider({
  apiBase,
  sessionId = 'default',
  children,
}: AgentRegistryProviderProps): ReactElement {
  const ref = useRef<Registry | null>(null);
  if (!ref.current) ref.current = createRegistry();
  const reg = ref.current;

  // Act path: react to the driver's latest intent.
  const activity = useAgentActivity();
  useEffect(() => {
    const i = activity?.intent;
    if (i && i.intent === 'act') reg.run(i.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activity?.tick]);

  // Read path: push a debounced snapshot on every change.
  useEffect(() => {
    if (!apiBase) return;
    const base = apiBase.replace(/\/$/, '');
    let timer: ReturnType<typeof setTimeout> | null = null;
    const push = (): void => {
      void fetch(`${base}/connector/ui/snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, snapshot: reg.snapshot() }),
      }).catch(() => {});
    };
    const schedule = (): void => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(push, 150);
    };
    const unsub = reg.subscribe(schedule);
    schedule();
    return () => {
      if (timer) clearTimeout(timer);
      unsub();
    };
  }, [apiBase, sessionId, reg]);

  return <RegistryCtx.Provider value={reg}>{children}</RegistryCtx.Provider>;
}

function useRegistry(): Registry | null {
  return useContext(RegistryCtx);
}

function AgentPage({
  name,
  children,
}: {
  name: string;
  description?: string;
  children: ReactNode;
}): ReactElement {
  const reg = useRegistry();
  useEffect(() => {
    reg?.setPage(name);
    return () => {
      if (reg?.getPage() === name) reg.setPage(null);
    };
  }, [reg, name]);
  return <PageCtx.Provider value={name}>{children}</PageCtx.Provider>;
}

function AgentData({
  name,
  description,
  value,
  children,
}: {
  name: string;
  description?: string;
  value: unknown;
  children: ReactNode;
}): ReactElement {
  const reg = useRegistry();
  const page = useContext(PageCtx);
  const full = scoped(page, name);
  useEffect(() => {
    reg?.setData({ name: full, description, value });
    return () => reg?.removeData(full);
  }, [reg, full, description, value]);
  return <>{children}</>;
}

function AgentButton({
  name,
  description,
  onAct,
  children,
}: {
  name: string;
  description?: string;
  onAct: () => void | Promise<void>;
  children: ReactNode;
}): ReactElement {
  const reg = useRegistry();
  const page = useContext(PageCtx);
  const full = scoped(page, name);
  const onActRef = useRef(onAct);
  onActRef.current = onAct;
  useEffect(() => {
    reg?.setAction({ name: full, description, onAct: () => onActRef.current() });
    return () => reg?.removeAction(full);
  }, [reg, full, description]);
  return (
    <span data-agent-control={full} style={{ display: 'contents' }}>
      {children}
    </span>
  );
}

export const Agent = { Page: AgentPage, Data: AgentData, Button: AgentButton };
```

- [ ] **Step 5: Add exports to `index.ts`**

Append to `minder_ui_sdk/src/index.ts`:

```ts
export { Agent, AgentRegistryProvider } from './agentSurface/AgentSurface';
export type { AgentRegistryProviderProps } from './agentSurface/AgentSurface';
export { createRegistry, MAX_VALUE_CHARS } from './agentSurface/registry';
export type { UiSnapshot, DataEntry, ActionEntry, Registry } from './agentSurface/registry';
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd minder_ui_sdk && npx vitest run tests/agentSurface.test.tsx`
Expected: PASS (3 tests)

- [ ] **Step 7: Run the full SDK suite to check no regressions**

Run: `cd minder_ui_sdk && npm run test`
Expected: PASS (all existing tests + the new ones)

- [ ] **Step 8: Commit**

```bash
git add minder_ui_sdk/src/agentDriver.tsx minder_ui_sdk/src/agentSurface/AgentSurface.tsx minder_ui_sdk/src/index.ts minder_ui_sdk/tests/agentSurface.test.tsx
git commit -m "feat(sdk): add Agent.Page/Data/Button wrappers + act intent"
```

---

### Task 3: Snapshot push debounce + payload assertion

**Files:**
- Test: `minder_ui_sdk/tests/agentSurfaceSnapshot.test.tsx`
- (No source change expected — this task verifies the push wiring added in Task 2. If a test reveals a bug, fix `AgentSurface.tsx`.)

**Interfaces:**
- Consumes: `AgentRegistryProvider`, `Agent` from Task 2.

- [ ] **Step 1: Write the failing test**

```tsx
// minder_ui_sdk/tests/agentSurfaceSnapshot.test.tsx
import { render, act } from '@testing-library/react';
import { AgentRegistryProvider, Agent } from '../src/agentSurface/AgentSurface';

beforeEach(() => {
  vi.useFakeTimers();
  (globalThis as any).fetch = vi.fn(() => Promise.resolve({ ok: true }));
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('POSTs a debounced snapshot with scoped names to /connector/ui/snapshot', () => {
  render(
    <AgentRegistryProvider apiBase="http://m/" sessionId="s1">
      <Agent.Page name="products" description="Kho">
        <Agent.Data name="list" description="rows" value={[{ id: 1 }]}>
          <div>t</div>
        </Agent.Data>
        <Agent.Button name="add" description="add" onAct={() => {}}>
          <button>Add</button>
        </Agent.Button>
      </Agent.Page>
    </AgentRegistryProvider>,
  );
  act(() => {
    vi.advanceTimersByTime(200);
  });
  const fetchMock = (globalThis as any).fetch as ReturnType<typeof vi.fn>;
  const calls = fetchMock.mock.calls;
  expect(calls.length).toBeGreaterThan(0);
  const [url, opts] = calls[calls.length - 1];
  expect(url).toBe('http://m/connector/ui/snapshot');
  const body = JSON.parse(opts.body);
  expect(body.session_id).toBe('s1');
  expect(body.snapshot.page).toBe('products');
  expect(body.snapshot.data.map((d: any) => d.name)).toContain('products.list');
  expect(body.snapshot.actions.map((a: any) => a.name)).toContain('products.add');
});
```

- [ ] **Step 2: Run test to verify it fails (or reveals a wiring bug)**

Run: `cd minder_ui_sdk && npx vitest run tests/agentSurfaceSnapshot.test.tsx`
Expected: If Task 2's push wiring is correct, this may already PASS. Treat a FAIL as a bug in `AgentSurface.tsx` push effect and fix it (URL, body shape, or debounce). Do not fake the assertion.

- [ ] **Step 3: If failing, fix the push effect in `AgentSurface.tsx`**

Ensure the effect builds the URL as `${apiBase.replace(/\/$/,'')}/connector/ui/snapshot`, posts `{ session_id, snapshot }`, and debounces with `setTimeout(..., 150)`. (Code already shown in Task 2, Step 4.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd minder_ui_sdk && npx vitest run tests/agentSurfaceSnapshot.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add minder_ui_sdk/tests/agentSurfaceSnapshot.test.tsx minder_ui_sdk/src/agentSurface/AgentSurface.tsx
git commit -m "test(sdk): assert debounced UI snapshot payload"
```

---

### Task 4: Backend — `act` intent + snapshot cache endpoint

**Files:**
- Modify: `minder_python_sdk/minder_python_sdk/ui.py` (`INTENT_TYPES` ~line 18; add `act` builder near other builders ~line 115-145)
- Modify: `minder_python_sdk/minder_python_sdk/connector.py` (`__init__` per-session state; add `POST /connector/ui/snapshot`; fold `ui_snapshot` into `GET /connector/context` ~line 926)
- Test: `minder_python_sdk/tests/test_agent_surface.py` (append)

**Interfaces:**
- Consumes: existing `push_ui_intent`, `is_intent`, `_session_from_headers`, `Request`.
- Produces:
  - `INTENT_TYPES` includes `"act"`; new builder `act(name: str) -> dict` returning `{"intent": "act", "name": name}`.
  - Connector holds `self._ui_snapshots: dict[str, dict]`.
  - `POST /connector/ui/snapshot` body `{"session_id": str, "snapshot": dict}` → stores, returns `{"ok": True}`.
  - `GET /connector/context` response gains `"ui_snapshot": <dict | None>` for the request's session.

- [ ] **Step 1: Write the failing test**

```python
# minder_python_sdk/tests/test_agent_surface.py  (append; keep existing imports/tests)
from fastapi.testclient import TestClient

from minder_python_sdk.ui import act, is_intent


def test_act_is_a_recognized_intent():
    intent = act("products.add")
    assert intent == {"intent": "act", "name": "products.add"}
    assert is_intent(intent) is True


def _client_with_snapshot_module():
    """Build a minimal connector app for snapshot round-trip.

    Reuse the same construction the other tests in this file use; if this file
    already has a `make_connector()`/fixture helper, call that instead of
    duplicating. This helper documents the required shape.
    """
    from minder_python_sdk.connector import Connector

    conn = Connector(name="snap_demo")
    return TestClient(conn.asgi())


def test_snapshot_round_trips_into_context():
    client = _client_with_snapshot_module()
    snap = {
        "page": "products",
        "data": [{"name": "products.list", "description": "rows", "value": [{"id": 1}]}],
        "actions": [{"name": "products.add", "description": "add"}],
    }
    r = client.post(
        "/connector/ui/snapshot",
        json={"session_id": "default", "snapshot": snap},
    )
    assert r.status_code == 200 and r.json()["ok"] is True

    ctx = client.get("/connector/context").json()
    assert ctx["ui_snapshot"] == snap
```

Note: `TestClient` GET `/connector/context` with no session header resolves to session `"default"` via `_session_from_headers` — confirm that default while implementing; if the helper returns `None`, treat `None` as `"default"` on both write and read.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd minder_python_sdk && python -m pytest tests/test_agent_surface.py -q`
Expected: FAIL — `ImportError: cannot import name 'act'` (and later, missing endpoint)

- [ ] **Step 3: Add `act` to `ui.py`**

In `minder_python_sdk/minder_python_sdk/ui.py`, extend the tuple (line 18):

```python
INTENT_TYPES = ("navigate", "fill", "focus", "highlight", "request_confirm", "submit", "act")
```

Add the builder next to the other intent builders (after `submit`, ~line 145):

```python
def act(name: str) -> dict:
    """Trigger a declarative ``Agent.Button`` by its scoped name (e.g.
    ``"products.add"``). Runs the button's ``onAct`` immediately on the client."""
    return {"intent": "act", "name": name}
```

Do NOT add an `act` branch to `UiSurface.validate` — client-declared actions are not part of the server surface, so `act` intents pass validation unchanged.

- [ ] **Step 4: Add snapshot state + endpoint + context fold-in in `connector.py`**

In `__init__`, next to the per-session UI bus (`self._ui_bus`), add:

```python
self._ui_snapshots: dict[str, dict] = {}
```

Add the endpoint near the other `/connector/ui/*` routes (after the `POST /connector/ui/intent` handler ~line 1039-1049):

```python
@app.post("/connector/ui/snapshot")
async def ui_snapshot(request: Request) -> dict:
    """Cache the frontend's declarative UI snapshot for one session so the
    agent can read what's currently on screen via ``/connector/context``."""
    body = await _json_body(request)
    session = body.get("session_id") or "default"
    self._ui_snapshots[session] = body.get("snapshot") or {}
    return {"ok": True}
```

In the `GET /connector/context` handler (line 926-952), add `ui_snapshot` to the returned dict:

```python
@app.get("/connector/context")
def context(request: Request) -> dict:
    principal = _principal_from_headers(request)
    autonomy = _autonomy_from_headers(request) or self.default_autonomy
    session = _session_from_headers(request) or "default"
    return {
        "module": self.name,
        "autonomy": autonomy,
        "principal": {
            "username": principal.username,
            "authenticated": principal.is_authenticated,
            "roles": principal.roles,
            "scopes": principal.scopes,
        },
        "actions": [
            {
                "name": t.name,
                "risk": t.risk,
                "read_only": t.read_only,
                "reversible": t.reversible,
                "undo": t.undo,
                "allowed": autonomy_allows(t.risk, autonomy),
            }
            for t in self._tools.values()
        ],
        "ui_snapshot": self._ui_snapshots.get(session),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd minder_python_sdk && python -m pytest tests/test_agent_surface.py -q`
Expected: PASS

- [ ] **Step 6: Run the module_sdk suite to check no regressions**

Run: `cd minder_python_sdk && python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add minder_python_sdk/minder_python_sdk/ui.py minder_python_sdk/minder_python_sdk/connector.py minder_python_sdk/tests/test_agent_surface.py
git commit -m "feat(connector): cache UI snapshot + accept act intent"
```

---

### Task 5: End-to-end in `module_template` (real run)

**Files:**
- Modify: `modules/module_template/frontend/src/dashboard.tsx` (mount `AgentRegistryProvider` inside `AgentDriverProvider`)
- Modify: `modules/module_template/frontend/src/panels/ProductsPanel.tsx` (wrap page, product list, submit button)

**Interfaces:**
- Consumes: `AgentRegistryProvider`, `Agent` from the SDK.

- [ ] **Step 1: Mount the registry provider in `dashboard.tsx`**

Add `AgentRegistryProvider` to the SDK import list, and wrap the existing subtree (inside `AgentDriverProvider`, around `ToastProvider`):

```tsx
import {
  MinderThemeProvider,
  useMinderTheme,
  AgentDriverProvider,
  AgentRegistryProvider,
  AgentPresence,
  Agent,
  type DashboardProps,
  type DashboardComponent,
} from "minder-ui-sdk";
```

```tsx
<AgentDriverProvider apiBase={apiBase} onNavigate={(route) => setTab(ROUTE_TO_TAB[route] ?? route)}>
  <AgentRegistryProvider apiBase={apiBase} sessionId="default">
    <ToastProvider>
      <Surface>
        <StatHeader apiBase={apiBase} />
        <Panel apiBase={apiBase} />
      </Surface>
      <AgentPresence apiBase={apiBase} />
    </ToastProvider>
  </AgentRegistryProvider>
</AgentDriverProvider>
```

- [ ] **Step 2: Wrap the Products panel content**

In `ProductsPanel.tsx`, import `Agent` from `minder-ui-sdk`. Wrap the panel's root return in `<Agent.Page name="products" description="Quản lý sản phẩm trong kho">`, wrap the product-list rendering in `<Agent.Data name="list" description="Sản phẩm đang hiển thị" value={products}>` (use the panel's existing products state variable name), and wrap the existing submit `motion.button` (line ~198, `data-agent-control="submit"`) in:

```tsx
<Agent.Button name="add" description="Thêm sản phẩm mới vào kho" onAct={submit}>
  {/* existing <motion.button ... onClick={submit}> ... </motion.button> */}
</Agent.Button>
```

Keep the existing `useAgentForm`/`data-agent-*` wiring intact — `Agent.*` is additive.

- [ ] **Step 3: Build the frontend to confirm it compiles**

Run: `cd modules/module_template/frontend && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Real end-to-end run**

Per `CLAUDE.md`, exercise the real running app (`export OPENAI_API_KEY=...` first if invoking the agent).

Start the module backend + frontend (module serves on `http://localhost:9300`), then verify both paths against the live connector:

```bash
# Read path: push a snapshot, confirm it surfaces in context
curl -s -X POST localhost:9300/connector/ui/snapshot \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"default","snapshot":{"page":"products","data":[{"name":"products.list","value":[{"id":1}]}],"actions":[{"name":"products.add","description":"add"}]}}'
curl -s localhost:9300/connector/context | python -m json.tool   # expect "ui_snapshot" populated

# Act path: emit an act intent for the wrapped button
curl -s -X POST localhost:9300/connector/ui/intent \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"default","intent":{"intent":"act","name":"products.add"}}'
```

In the browser (host at the web UI, module dashboard on the Products tab): confirm (a) the snapshot POST fires on load (Network tab shows `/connector/ui/snapshot` with the real product list), and (b) firing the act intent triggers the Add-product submit and the ghost cursor points at the wrapped control (`data-agent-control="products.add"`).

- [ ] **Step 5: Commit**

```bash
git add modules/module_template/frontend/src/dashboard.tsx modules/module_template/frontend/src/panels/ProductsPanel.tsx
git commit -m "feat(module_template): wrap Products panel with Agent.* surface"
```

---

## Self-Review

**Spec coverage:**
- `Agent.Page/Data/Button` transparent wrappers → Task 2. ✓
- Browser registry as source of truth → Task 1. ✓
- Read (snapshot) path over connector → Task 2 (push) + Task 4 (cache + context fold-in). ✓
- Act path via existing intent bus, one new `act` variant → Task 2 (frontend) + Task 4 (backend `is_intent`). ✓
- No approval, immediate `onAct` → registry `run()` (Task 1), no gate. ✓
- Page-scoped names → `scoped()` (Task 2), verified in Tasks 2-3. ✓
- 32 KB value cap + `truncated` → Task 1. ✓
- Presence layer benefits via `data-agent-control` → Task 2 `AgentButton`, verified in Task 5. ✓
- Coexist with `useAgentForm` → Task 5 keeps existing wiring. ✓

**Placeholder scan:** No TBD/TODO; every code step shows real code; every test shows real assertions.

**Type consistency:** `createRegistry`/`Registry`/`UiSnapshot`/`MAX_VALUE_CHARS` defined in Task 1 and consumed by the same names in Task 2 exports and Task 3 tests. `act(name)` / `{"intent":"act","name"}` shape identical across frontend (Task 2 `UiIntent`), backend builder (Task 4), and E2E curl (Task 5). Snapshot payload `{session_id, snapshot}` and `snapshot.{page,data,actions}` identical across Task 2 push, Task 3 assertion, Task 4 endpoint/test, Task 5 curl.
