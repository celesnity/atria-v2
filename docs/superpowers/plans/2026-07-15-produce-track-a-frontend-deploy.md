# Produce Track A — Frontend + Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the already-built Produce Track A backend (11 epics, REST, 29 tests) into a runnable standalone MES: a persona-based React dashboard wired to the REST API, served by the module's own FastAPI, plus Docker/Compose deployment.

**Architecture:** Track A is pure human-operated software — no `minder_python_sdk` import, no `@conn.tool`, no `/connector/*`. The FastAPI backend (already exposes `/config`, `/work`, `/sop`, `/wip`, `/downtime`, `/scrap`, `/oee`, `/setup`, `/handover`, `/exception`, `/report`) additionally mounts the built React `dist/` as static files and enables CORS for local dev. The frontend is a Module-Federation build (mirrors `module_template`) but ALSO ships a standalone SPA entry so operators use it without the Minder host. Panels fetch Track A REST directly via a shared typed `api()` helper. Hybrid UI: 5 persona tabs (top, from manifest) → epic panels inside each persona route.

**Tech Stack:** FastAPI + SQLAlchemy (backend, done); React 18.3.1 + Vite 5 + `@module-federation/vite` + `minder-ui-sdk` (from source alias) + `lucide-react` + `motion` (frontend); Docker multi-stage; Celery + Redis (worker, minimal).

## Global Constraints

- **Track A purity:** no `import minder`, no `minder_python_sdk`, no `@conn.tool`, no `/connector/*` route or fetch. Frontend talks ONLY to Track A REST (`/config`, `/work`, …). Copied verbatim from spec: "Produce như một phần mềm thuần … không có AI trong đây."
- **Python:** 3.12; line length 100 (Black + Ruff); Google-style docstrings; `mypy` strict on public APIs.
- **Naming:** DB tables `pr_*`; env vars `PR_*`; service port `9310`; module id `produce`.
- **Frontend:** React `^18.3.1` (singleton in federation); `minder-ui-sdk` consumed from source via vite alias `../../../minder_ui_sdk/src/index.ts`; TS `strict: true`; theme via `MinderThemeProvider` / `useMinderTheme().tokens`.
- **Tests:** backend `uv run --no-sync pytest` from `modules/produce/backend/` (has `conftest.py`); each test rebinds the lazy engine to `sqlite://` via monkeypatch (`db._engine`, `db._SessionLocal`, `db.get_engine`). `tests/` is globally gitignored — stage test files with `git add -f`.
- **Commits:** Conventional Commits; NO `Co-Authored-By: Claude` trailer.
- **Cross-epic backend calls** go through service functions only, never another epic's models.

---

## File Structure

**Backend (modify):**
- `modules/produce/backend/app.py` — add CORS + StaticFiles mount of `frontend_dist/`.
- `modules/produce/backend/domain/config/{service,routes}.py` — add threshold + skill endpoints (P-CFG-03/04) the Admin panel reads.
- `modules/produce/backend/celery_app.py` — **create**; Celery app on `PR_REDIS_URL`.
- `modules/produce/worker/tasks.py` — replace stub with one real periodic-style task (OEE snapshot log).
- `modules/produce/backend/requirements.txt` — already has fastapi/uvicorn/sqlalchemy/celery/redis; no change unless noted.

**Frontend (create/replace):**
- `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx` (standalone entry).
- `frontend/src/api.ts` — typed fetch helper + `useApi` hook.
- `frontend/src/ui/{Section,DataTable,Field,Button,Toast}.tsx` — shared primitives.
- `frontend/src/theme.ts` — status color map (already stubbed; replace).
- `frontend/src/dashboard.tsx` — persona-tab shell (replace stub).
- `frontend/src/routes/{operator,leader,supervisor,manager,admin}.tsx` — compose epic panels (replace stubs).
- `frontend/src/panels/*Panel.tsx` — 11 epic panels wired to REST (replace stubs).

**Deployment (create):**
- `modules/produce/backend/Dockerfile`, `modules/produce/worker/Dockerfile`, `modules/produce/docker-compose.snippet.yml`, `modules/produce/README.md`.

---

## Phase 1 — Backend: serve UI + close config gaps

### Task 1: CORS + static frontend mount

**Files:**
- Modify: `modules/produce/backend/app.py`
- Test: `modules/produce/backend/tests/test_smoke.py`

**Interfaces:**
- Produces: `app.app` still exposes `/health`; now also serves `GET /` and `/assets/*` from `frontend_dist/` when that dir exists; adds permissive CORS for dev origins.

- [ ] **Step 1: Write the failing test** — append to `tests/test_smoke.py`:

```python
def test_cors_header_present():
    from fastapi.testclient import TestClient
    import app

    c = TestClient(app.app)
    r = c.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_smoke.py::test_cors_header_present -v`
Expected: FAIL (no `access-control-allow-origin` header).

- [ ] **Step 3: Implement** — edit `app.py`. Add imports near the top:

```python
import os

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
```

After `app = FastAPI(title="Produce", version="0.1.0", lifespan=lifespan)` and BEFORE the router loop, add CORS:

```python
# Track A is standalone software; the UI (served from frontend_dist or a dev
# vite server) is the only client. Permissive CORS keeps local dev simple.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

At the END of the file (after the `/health` route), mount the built UI when present:

```python
# Serve the built React dashboard as a standalone SPA when it has been built
# into ./frontend_dist (Docker copies it there). No-op in a bare checkout.
_DIST = os.environ.get("PR_DASHBOARD_DIST", os.path.join(os.path.dirname(__file__), "frontend_dist"))
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="ui")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync pytest tests/test_smoke.py -v`
Expected: PASS (both smoke tests).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/app.py
git add -f modules/produce/backend/tests/test_smoke.py
git commit -m "feat(produce): CORS + static UI mount on Track A backend"
```

### Task 2: Config threshold + skill endpoints (P-CFG-03/04)

**Files:**
- Modify: `modules/produce/backend/domain/config/service.py`, `modules/produce/backend/domain/config/routes.py`
- Test: `modules/produce/backend/tests/test_config.py`

**Interfaces:**
- Produces: `service.create_threshold(line_id, metric, op, value) -> dict`, `service.list_thresholds(line_id) -> list[dict]`, `service.create_skill(code, name) -> dict`, `service.list_skills() -> list[dict]`. Routes: `POST/GET /config/lines/{line_id}/thresholds`, `POST/GET /config/skills`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_config.py`:

```python
def test_threshold_and_skill_crud():
    from domain.config import service

    line = service.create_line("L9", "Line 9")["id"]
    th = service.create_threshold(line, "downtime_minutes", ">", 15)
    assert th["metric"] == "downtime_minutes" and th["op"] == ">"
    assert service.list_thresholds(line)[0]["value"] == 15

    sk = service.create_skill("WELD", "Welding")
    assert sk["code"] == "WELD"
    assert service.list_skills()[0]["name"] == "Welding"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync pytest tests/test_config.py::test_threshold_and_skill_crud -v`
Expected: FAIL (`AttributeError: module ... has no attribute 'create_threshold'`).

- [ ] **Step 3: Implement** — append to `domain/config/service.py` (imports at top already have `select`, `db_session`; extend the model import line to include `PrSkill, PrThreshold`):

```python
# --- Threshold (P-CFG-04) -------------------------------------------------------
def create_threshold(line_id: int, metric: str, op: str, value: float) -> dict:
    with db_session() as s:
        th = PrThreshold(line_id=line_id, metric=metric, op=op, value=value)
        s.add(th)
        s.flush()
        return th.as_dict()


def list_thresholds(line_id: int) -> list[dict]:
    with db_session() as s:
        stmt = select(PrThreshold).where(PrThreshold.line_id == line_id).order_by(PrThreshold.id)
        return [r.as_dict() for r in s.scalars(stmt).all()]


# --- Skill (P-CFG-03) -----------------------------------------------------------
def create_skill(code: str, name: str) -> dict:
    with db_session() as s:
        sk = PrSkill(code=code, name=name)
        s.add(sk)
        s.flush()
        return sk.as_dict()


def list_skills() -> list[dict]:
    with db_session() as s:
        return [r.as_dict() for r in s.scalars(select(PrSkill).order_by(PrSkill.id)).all()]
```

Update the model import in `service.py` from:

```python
from .models import PrLine, PrOperation, PrPart, PrStation
```

to:

```python
from .models import PrLine, PrOperation, PrPart, PrSkill, PrStation, PrThreshold
```

Append to `domain/config/routes.py` (before end of file):

```python
class ThresholdIn(BaseModel):
    metric: str = Field(min_length=1, max_length=32)
    op: str = Field(default=">", max_length=4)
    value: float


class SkillIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


@router.get("/lines/{line_id}/thresholds")
def get_thresholds(line_id: int) -> list[dict]:
    return service.list_thresholds(line_id)


@router.post("/lines/{line_id}/thresholds")
def post_threshold(line_id: int, body: ThresholdIn) -> dict:
    return service.create_threshold(line_id, body.metric, body.op, body.value)


@router.get("/skills")
def get_skills() -> list[dict]:
    return service.list_skills()


@router.post("/skills")
def post_skill(body: SkillIn) -> dict:
    return service.create_skill(body.code, body.name)
```

- [ ] **Step 4: Run test + lint**

Run: `uv run --no-sync pytest tests/test_config.py -v && cd ../../.. && uv run --no-sync ruff check modules/produce/backend && cd modules/produce/backend`
Expected: tests PASS; ruff "All checks passed!".

- [ ] **Step 5: Commit**

```bash
git add modules/produce/backend/domain/config/service.py modules/produce/backend/domain/config/routes.py
git add -f modules/produce/backend/tests/test_config.py
git commit -m "feat(produce): config threshold + skill endpoints (P-CFG-03/04)"
```

---

## Phase 2 — Frontend foundation

### Task 3: Build config (package.json, vite, tsconfig, index.html, standalone entry)

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`
- Modify: nothing else this task.

**Interfaces:**
- Produces: `npm run build` emits `dist/` with both `remoteEntry.js` (federation, for host embedding) and `index.html` (standalone SPA). `main.tsx` mounts `<Dashboard apiBase="" activeTab={firstTab} theme="dark" />` at `#root`.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "produce-frontend",
  "private": true,
  "type": "module",
  "scripts": { "build": "vite build", "dev": "vite" },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "motion": "^11.11.0",
    "lucide-react": "^0.553.0"
  },
  "devDependencies": {
    "@module-federation/vite": "^1.16.14",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.4.0",
    "vite": "^5.1.4"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```ts
import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';
import { minderTabsSync } from '../../../minder_ui_sdk/src/vitePlugin';

const here = dirname(fileURLToPath(import.meta.url));
const sdk = resolve(here, '../../../minder_ui_sdk/src');

// Federation remote is served cross-origin by the host; bundled asset URLs must
// be fully-qualified back to THIS module's public origin.
const publicBase = (process.env.PR_PUBLIC_BASE || 'http://localhost:9310').replace(/\/$/, '');
const assetBase = `${publicBase}/dashboard/`;

export default defineConfig({
  experimental: {
    renderBuiltUrl(filename) {
      return assetBase + filename;
    },
  },
  resolve: {
    alias: { 'minder-ui-sdk': resolve(sdk, 'index.ts') },
  },
  plugins: [
    react(),
    minderTabsSync(),
    federation({
      name: 'produce',
      filename: 'remoteEntry.js',
      exposes: { './Dashboard': './src/dashboard.tsx' },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
    }),
  ],
  build: { outDir: 'dist', target: 'esnext' },
  server: { origin: 'http://localhost:9310', port: 5173 },
});
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ESNext", "useDefineForClassFields": true, "lib": ["DOM", "DOM.Iterable", "ESNext"],
    "module": "ESNext", "skipLibCheck": true, "moduleResolution": "bundler",
    "resolveJsonModule": true, "isolatedModules": true, "noEmit": true, "jsx": "react-jsx",
    "strict": true,
    "baseUrl": ".",
    "paths": { "minder-ui-sdk": ["../../../minder_ui_sdk/src/index.ts"] }
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create `frontend/index.html`**

```html
<!doctype html>
<html>
  <head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>Produce</title></head>
  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

- [ ] **Step 5: Create `frontend/src/main.tsx`** (standalone SPA entry — used when operators run Track A without the Minder host)

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './dashboard';
import { TABS } from './dashboard.tabs';

// Standalone: same-origin API (backend serves this dist), dark theme by default.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Dashboard apiBase="" activeTab={TABS[0].id} theme="dark" />
  </StrictMode>,
);
```

- [ ] **Step 6: Install + verify build tooling resolves** (build will fail until panels exist; just verify deps install)

Run: `cd modules/produce/frontend && npm install`
Expected: `node_modules/` created, no resolution errors for listed deps.

- [ ] **Step 7: Commit**

```bash
cd /Users/anlnm/Desktop/Project/opendev-py
git add modules/produce/frontend/package.json modules/produce/frontend/package-lock.json modules/produce/frontend/vite.config.ts modules/produce/frontend/tsconfig.json modules/produce/frontend/index.html modules/produce/frontend/src/main.tsx
git commit -m "feat(produce): frontend build config + standalone SPA entry"
```

### Task 4: Shared API helper + UI primitives

**Files:**
- Create: `frontend/src/api.ts`, `frontend/src/ui/Section.tsx`, `frontend/src/ui/DataTable.tsx`, `frontend/src/ui/Field.tsx`, `frontend/src/ui/Button.tsx`, `frontend/src/ui/Toast.tsx`
- Replace: `frontend/src/theme.ts`

**Interfaces:**
- Produces (consumed by every panel):
  - `api<T>(base: string, path: string, init?: RequestInit): Promise<T>` — JSON fetch; throws `Error(detail)` on non-2xx (reads FastAPI `{detail}` for 409s).
  - `useApi<T>(base, path, deps?) => { data: T | null, loading: boolean, reload: () => void, error: string | null }`.
  - `<Section title actions?>…</Section>` — titled card container.
  - `<DataTable columns={[{key,label,render?}]} rows={T[]} empty? />`.
  - `<Field label>…</Field>`, `<TextInput value onChange placeholder? type? />`, `<NumberInput …>`.
  - `<Button onClick disabled? variant?>` (`variant`: `primary` | `ghost` | `danger`).
  - `<ToastProvider>` + `useToast()` → `{ notify(msg, kind?) }` (`kind`: `ok` | `err`).
  - `statusColor(tokens, status): string` (from theme.ts).

- [ ] **Step 1: Create `frontend/src/api.ts`**

```ts
import { useCallback, useEffect, useState } from 'react';

/** JSON fetch against Track A REST. Throws Error(detail) on non-2xx. */
export async function api<T = unknown>(base: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Read hook: fetches on mount and whenever `deps` change; exposes reload(). */
export function useApi<T = unknown>(base: string, path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    api<T>(base, path)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, path, ...deps]);

  useEffect(() => { reload(); }, [reload]);
  return { data, loading, reload, error };
}
```

- [ ] **Step 2: Replace `frontend/src/theme.ts`**

```ts
import type { MinderTokens } from 'minder-ui-sdk';

/** Map a produce status string to a token color. */
export function statusColor(tokens: MinderTokens, status: string): string {
  switch (status) {
    case 'queued': case 'idle': case 'open': case 'draft':
      return tokens.warning;
    case 'assigned': case 'in_progress': case 'running': case 'triaged': case 'setup':
      return tokens.primary;
    case 'done': case 'resolved': case 'approved': case 'released': case 'acknowledged':
      return tokens.success;
    case 'blocked': case 'down': case 'held': case 'escalated': case 'aborted': case 'retired':
      return tokens.error;
    default:
      return tokens.textMuted;
  }
}
```

- [ ] **Step 3: Create `frontend/src/ui/Section.tsx`**

```tsx
import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export default function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <section style={{ background: tokens.surface, border: `1px solid ${tokens.border}`, borderRadius: 12, padding: 16, marginBottom: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h3 style={{ margin: 0, color: tokens.text, fontSize: 15, fontWeight: 600 }}>{title}</h3>
        <div style={{ display: 'flex', gap: 8 }}>{actions}</div>
      </div>
      {children}
    </section>
  );
}
```

- [ ] **Step 4: Create `frontend/src/ui/DataTable.tsx`**

```tsx
import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export interface Column<T> { key: string; label: string; render?: (row: T) => ReactNode; }

export default function DataTable<T extends Record<string, unknown>>({ columns, rows, empty = 'No data' }: { columns: Column<T>[]; rows: T[]; empty?: string }) {
  const { tokens } = useMinderTheme();
  if (!rows.length) return <div style={{ color: tokens.textMuted, padding: '24px 0', textAlign: 'center', fontSize: 13 }}>{empty}</div>;
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: 'left', padding: '8px 10px', color: tokens.textMuted, borderBottom: `1px solid ${tokens.border}`, fontWeight: 600 }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={(row.id as number) ?? i}>
              {columns.map((c) => (
                <td key={c.key} style={{ padding: '8px 10px', color: tokens.text, borderBottom: `1px solid ${tokens.border}` }}>
                  {c.render ? c.render(row) : String(row[c.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/ui/Field.tsx`**

```tsx
import type { ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

export function Field({ label, children }: { label: string; children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: tokens.textMuted }}>
      {label}
      {children}
    </label>
  );
}

function inputStyle(tokens: ReturnType<typeof useMinderTheme>['tokens']) {
  return { background: tokens.bg, border: `1px solid ${tokens.border}`, borderRadius: 8, padding: '7px 10px', color: tokens.text, fontSize: 13 } as const;
}

export function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const { tokens } = useMinderTheme();
  return <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} style={inputStyle(tokens)} />;
}

export function NumberInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { tokens } = useMinderTheme();
  return <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))} style={inputStyle(tokens)} />;
}
```

- [ ] **Step 6: Create `frontend/src/ui/Button.tsx`**

```tsx
import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { useMinderTheme } from 'minder-ui-sdk';

export default function Button({ onClick, disabled, variant = 'primary', children }: { onClick: () => void; disabled?: boolean; variant?: 'primary' | 'ghost' | 'danger'; children: ReactNode }) {
  const { tokens } = useMinderTheme();
  const bg = variant === 'primary' ? tokens.primary : variant === 'danger' ? tokens.error : 'transparent';
  const color = variant === 'ghost' ? tokens.text : '#fff';
  const border = variant === 'ghost' ? `1px solid ${tokens.border}` : 'none';
  return (
    <motion.button
      whileHover={{ scale: disabled ? 1 : 1.03 }}
      whileTap={{ scale: disabled ? 1 : 0.97 }}
      onClick={onClick}
      disabled={disabled}
      style={{ background: bg, color, border, borderRadius: 8, padding: '7px 12px', fontSize: 13, fontWeight: 500, cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.6 : 1 }}
    >
      {children}
    </motion.button>
  );
}
```

- [ ] **Step 7: Create `frontend/src/ui/Toast.tsx`**

```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';

interface Toast { id: number; msg: string; kind: 'ok' | 'err'; }
const Ctx = createContext<{ notify: (msg: string, kind?: 'ok' | 'err') => void }>({ notify: () => {} });
export function useToast() { return useContext(Ctx); }

export function ToastProvider({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((msg: string, kind: 'ok' | 'err' = 'ok') => {
    const id = toasts.length + 1 + Math.floor(performance.now());
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, [toasts.length]);
  return (
    <Ctx.Provider value={{ notify }}>
      {children}
      <div style={{ position: 'fixed', bottom: 16, right: 16, display: 'flex', flexDirection: 'column', gap: 8, zIndex: 1000 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{ background: t.kind === 'ok' ? tokens.success : tokens.error, color: '#fff', borderRadius: 8, padding: '8px 14px', fontSize: 13 }}>{t.msg}</div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
```

- [ ] **Step 8: Commit**

```bash
git add modules/produce/frontend/src/api.ts modules/produce/frontend/src/theme.ts modules/produce/frontend/src/ui
git commit -m "feat(produce): shared api helper + UI primitives"
```

### Task 5: Dashboard shell (persona tabs → persona routes)

**Files:**
- Replace: `frontend/src/dashboard.tsx`, `frontend/src/dashboard.tabs.ts`

**Interfaces:**
- Consumes: `TABS` (persona list), the 5 route components (Task 6+ create them; import them here). `DashboardProps` from `minder-ui-sdk` (`{ apiBase, activeTab, theme }`).
- Produces: `default` export `Dashboard` — renders a top persona tab row and the active persona route, wrapped in `MinderThemeProvider` + `ToastProvider`. NO agent providers (Track A).

- [ ] **Step 1: Replace `frontend/src/dashboard.tabs.ts`**

```ts
import type { TabMeta } from 'minder-ui-sdk';

// Persona-based tabs (hybrid: persona route -> epic panels inside).
export const TABS: TabMeta[] = [
  { id: 'operator', label: 'Operator', icon: 'user' },
  { id: 'leader', label: 'Tổ trưởng', icon: 'users' },
  { id: 'supervisor', label: 'Quản ca', icon: 'clipboard-check' },
  { id: 'manager', label: 'Quản lý xưởng', icon: 'bar-chart' },
  { id: 'admin', label: 'FDE / Admin', icon: 'settings' },
];
```

- [ ] **Step 2: Replace `frontend/src/dashboard.tsx`**

```tsx
import { useEffect, useState, type ReactNode } from 'react';
import { MinderThemeProvider, useMinderTheme, type DashboardProps } from 'minder-ui-sdk';
import { ToastProvider } from './ui/Toast';
import { TABS } from './dashboard.tabs';
import OperatorRoute from './routes/operator';
import LeaderRoute from './routes/leader';
import SupervisorRoute from './routes/supervisor';
import ManagerRoute from './routes/manager';
import AdminRoute from './routes/admin';

const ROUTES: Record<string, React.ComponentType<{ apiBase: string }>> = {
  operator: OperatorRoute,
  leader: LeaderRoute,
  supervisor: SupervisorRoute,
  manager: ManagerRoute,
  admin: AdminRoute,
};

function TabBar({ tab, setTab }: { tab: string; setTab: (t: string) => void }) {
  const { tokens } = useMinderTheme();
  return (
    <div style={{ display: 'flex', gap: 4, padding: '10px 16px', borderBottom: `1px solid ${tokens.border}`, background: tokens.surfaceAlt }}>
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => setTab(t.id)}
          style={{
            background: tab === t.id ? tokens.primary : 'transparent',
            color: tab === t.id ? '#fff' : tokens.textMuted,
            border: 'none', borderRadius: 8, padding: '6px 14px', fontSize: 13, fontWeight: 500, cursor: 'pointer',
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Surface({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <div data-produce-dashboard="" style={{ minHeight: '100%', background: tokens.bg, color: tokens.text, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {children}
    </div>
  );
}

export default function Dashboard({ apiBase, activeTab, theme }: DashboardProps) {
  const [tab, setTab] = useState<string>(activeTab ?? TABS[0].id);
  useEffect(() => { if (activeTab) setTab(activeTab); }, [activeTab]);
  const Route = ROUTES[tab] ?? ROUTES.operator;
  return (
    <MinderThemeProvider theme={theme}>
      <ToastProvider>
        <Surface>
          <TabBar tab={tab} setTab={setTab} />
          <div style={{ padding: 16 }}>
            <Route apiBase={apiBase} />
          </div>
        </Surface>
      </ToastProvider>
    </MinderThemeProvider>
  );
}
```

- [ ] **Step 3: Commit** (build still red until routes exist — that's expected; commit the shell)

```bash
git add modules/produce/frontend/src/dashboard.tsx modules/produce/frontend/src/dashboard.tabs.ts
git commit -m "feat(produce): persona-tab dashboard shell (Track A)"
```

---

## Phase 3 — Epic panels (wired to REST)

Every panel is a default-export React component taking `{ apiBase }`, using `useApi`/`api` from `../api`, primitives from `../ui/*`, and `useToast()`. Each panel that mutates calls `api(...)` then `reload()` and `notify(...)`. A 409 from the backend surfaces via the thrown `Error(detail)` → `notify(msg, 'err')` (this is how poka-yoke / guardrail messages reach the operator).

> **Line-context convention:** panels needing a `line_id`/`shift_id` read it from a small numeric input at the top of the panel (state `lineId`, default `1`). Real deployments seed lines via the Admin panel; the input lets a demo pick which line to view.

### Task 6: ConfigPanel (E11 — Admin)

**Files:**
- Replace: `frontend/src/panels/ConfigPanel.tsx`

**Interfaces:**
- Consumes: `GET/POST /config/lines`, `GET/POST /config/lines/{id}/stations`, `GET/POST /config/lines/{id}/operations`, `GET/POST /config/parts`.
- Produces: default export `ConfigPanel`.

- [ ] **Step 1: Write `frontend/src/panels/ConfigPanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, TextInput, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function ConfigPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [lineCode, setLineCode] = useState('');
  const [lineName, setLineName] = useState('');
  const [partCode, setPartCode] = useState('');
  const [partName, setPartName] = useState('');
  const [ict, setIct] = useState(0);

  const lines = useApi<Array<Record<string, unknown>>>(apiBase, '/config/lines');
  const stations = useApi<Array<Record<string, unknown>>>(apiBase, `/config/lines/${lineId}/stations`, [lineId]);
  const parts = useApi<Array<Record<string, unknown>>>(apiBase, '/config/parts');

  const addLine = async () => {
    try {
      await api(apiBase, '/config/lines', { method: 'POST', body: JSON.stringify({ code: lineCode, name: lineName }) });
      setLineCode(''); setLineName(''); lines.reload(); notify('Đã tạo line');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const addPart = async () => {
    try {
      await api(apiBase, '/config/parts', { method: 'POST', body: JSON.stringify({ code: partCode, name: partName, ideal_cycle_time: ict || null }) });
      setPartCode(''); setPartName(''); setIct(0); parts.reload(); notify('Đã tạo phiên bản part');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  return (
    <>
      <Section title="Lines" actions={<Button onClick={addLine} disabled={!lineCode || !lineName}>+ Line</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Code"><TextInput value={lineCode} onChange={setLineCode} placeholder="L1" /></Field>
          <Field label="Name"><TextInput value={lineName} onChange={setLineName} placeholder="Line 1" /></Field>
        </div>
        <DataTable columns={[{ key: 'id', label: 'ID' }, { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }]} rows={lines.data ?? []} empty="Chưa có line" />
      </Section>

      <Section title={`Stations · line ${lineId}`} actions={<Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>}>
        <DataTable columns={[{ key: 'id', label: 'ID' }, { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }, { key: 'seq', label: 'Seq' }]} rows={stations.data ?? []} empty="Chưa có station" />
      </Section>

      <Section title="Parts (versioned)" actions={<Button onClick={addPart} disabled={!partCode || !partName}>+ Version</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Code"><TextInput value={partCode} onChange={setPartCode} placeholder="PN-1" /></Field>
          <Field label="Name"><TextInput value={partName} onChange={setPartName} /></Field>
          <Field label="Ideal cycle (s)"><NumberInput value={ict} onChange={setIct} /></Field>
        </div>
        <DataTable columns={[{ key: 'code', label: 'Code' }, { key: 'version', label: 'Ver' }, { key: 'name', label: 'Name' }, { key: 'ideal_cycle_time', label: 'ICT (s)' }]} rows={parts.data ?? []} empty="Chưa có part" />
      </Section>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/ConfigPanel.tsx
git commit -m "feat(produce): ConfigPanel wired to /config (E11)"
```

### Task 7: SopPanel (E2 — Admin authoring + Operator execution)

**Files:**
- Replace: `frontend/src/panels/SopPanel.tsx`

**Interfaces:**
- Consumes: `POST /sop/sops`, `POST /sop/sops/{id}/versions`, `POST /sop/versions/{id}/publish`, `GET /sop/sops/{id}/released`, `POST /sop/step-confirms`, `GET /sop/jobs/{job_id}/progress`.
- Produces: default export `SopPanel`.

- [ ] **Step 1: Write `frontend/src/panels/SopPanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, TextInput, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function SopPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [sopId, setSopId] = useState(1);
  const [versionId, setVersionId] = useState(1);
  const [jobId, setJobId] = useState(1);
  const [stepIndex, setStepIndex] = useState(0);
  const [value, setValue] = useState(0);

  const released = useApi<Record<string, unknown> | null>(apiBase, `/sop/sops/${sopId}/released`, [sopId]);
  const progress = useApi<Array<Record<string, unknown>>>(apiBase, `/sop/jobs/${jobId}/progress`, [jobId]);

  const publish = async () => {
    try { await api(apiBase, `/sop/versions/${versionId}/publish`, { method: 'POST' }); released.reload(); notify('Đã phát hành bản duyệt'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const confirm = async () => {
    try {
      await api(apiBase, '/sop/step-confirms', { method: 'POST', body: JSON.stringify({ job_id: jobId, sop_version_id: versionId, step_index: stepIndex, value: value || null }) });
      progress.reload(); notify(`Đã xác nhận bước ${stepIndex}`);
    } catch (e) { notify(String((e as Error).message), 'err'); }  // poka-yoke 409 lands here
  };

  const steps = (released.data?.steps as Array<Record<string, unknown>>) ?? [];

  return (
    <>
      <Section title="SOP đã phát hành" actions={<><Field label="SOP id"><NumberInput value={sopId} onChange={setSopId} /></Field><Field label="Version id"><NumberInput value={versionId} onChange={setVersionId} /></Field><Button onClick={publish}>Publish</Button></>}>
        <DataTable columns={[{ key: 'name', label: 'Step' }, { key: 'required', label: 'Bắt buộc', render: (r) => (r.required ? '✓' : '') }, { key: 'min', label: 'Min' }, { key: 'max', label: 'Max' }]} rows={steps} empty="Chưa có bản approved" />
      </Section>

      <Section title="Xác nhận bước (poka-yoke)" actions={<Button onClick={confirm}>Confirm step</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Job id"><NumberInput value={jobId} onChange={setJobId} /></Field>
          <Field label="Step index"><NumberInput value={stepIndex} onChange={setStepIndex} /></Field>
          <Field label="Giá trị đo"><NumberInput value={value} onChange={setValue} /></Field>
        </div>
        <DataTable columns={[{ key: 'step_index', label: 'Bước' }, { key: 'value', label: 'Giá trị' }, { key: 'confirmed_at', label: 'Lúc' }]} rows={progress.data ?? []} empty="Chưa xác nhận bước nào" />
      </Section>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/SopPanel.tsx
git commit -m "feat(produce): SopPanel wired to /sop with poka-yoke feedback (E2)"
```

### Task 8: WorkPanel (E1 — Operator queue + Leader board)

**Files:**
- Replace: `frontend/src/panels/WorkPanel.tsx`

**Interfaces:**
- Consumes: `GET /work/queue/{assignee_id}`, `GET /work/board/{line_id}`, `POST /work/tasks`, `POST /work/tasks/{id}/assign`, `POST /work/tasks/{id}/claim`.
- Produces: default export `WorkPanel` taking `{ apiBase, mode }` where `mode: 'queue' | 'board'` (default `'board'`).

- [ ] **Step 1: Write `frontend/src/panels/WorkPanel.tsx`**

```tsx
import { useState } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, TextInput, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';
import { statusColor } from '../theme';

export default function WorkPanel({ apiBase, mode = 'board' }: { apiBase: string; mode?: 'queue' | 'board' }) {
  const { tokens } = useMinderTheme();
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [operator, setOperator] = useState('op1');

  const board = useApi<Array<Record<string, unknown>>>(apiBase, `/work/board/${lineId}`, [lineId]);
  const queue = useApi<Array<Record<string, unknown>>>(apiBase, `/work/queue/${operator}`, [operator]);
  const active = mode === 'queue' ? queue : board;

  const addTask = async () => {
    try { await api(apiBase, '/work/tasks', { method: 'POST', body: JSON.stringify({ line_id: lineId }) }); board.reload(); notify('Đã tạo task'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const claim = async (id: number) => {
    try { await api(apiBase, `/work/tasks/${id}/claim`, { method: 'POST', body: JSON.stringify({ assignee_id: operator }) }); active.reload(); notify('Đã nhận task'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const assign = async (id: number) => {
    try { await api(apiBase, `/work/tasks/${id}/assign`, { method: 'POST', body: JSON.stringify({ assignee_id: operator }) }); active.reload(); notify('Đã gán task'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const statusCell = (r: Record<string, unknown>) => {
    const c = statusColor(tokens, String(r.status));
    return <span style={{ color: c, background: `${c}18`, borderRadius: 12, padding: '2px 8px', fontSize: 12 }}>{String(r.status)}</span>;
  };

  return (
    <Section
      title={mode === 'queue' ? `Hàng đợi · ${operator}` : `Board tổ · line ${lineId}`}
      actions={mode === 'queue'
        ? <Field label="Operator"><TextInput value={operator} onChange={setOperator} /></Field>
        : <><Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field><Field label="Operator"><TextInput value={operator} onChange={setOperator} /></Field><Button onClick={addTask}>+ Task</Button></>}
    >
      <DataTable
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'priority', label: 'Ưu tiên' },
          { key: 'assignee_id', label: 'Người làm' },
          { key: 'status', label: 'Trạng thái', render: statusCell },
          { key: 'act', label: '', render: (r) => (
            <div style={{ display: 'flex', gap: 6 }}>
              <Button variant="ghost" onClick={() => claim(r.id as number)}>Claim</Button>
              {mode === 'board' && <Button variant="ghost" onClick={() => assign(r.id as number)}>Assign</Button>}
            </div>
          ) },
        ]}
        rows={active.data ?? []}
        empty={mode === 'queue' ? 'Hàng đợi trống' : 'Chưa có task'}
      />
    </Section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/WorkPanel.tsx
git commit -m "feat(produce): WorkPanel queue+board wired to /work (E1)"
```

### Task 9: WipPanel (E3 — Operator)

**Files:**
- Replace: `frontend/src/panels/WipPanel.tsx`

**Interfaces:**
- Consumes: `POST /wip/jobs`, `POST /wip/jobs/{id}/complete`, `POST /wip/jobs/{id}/scan`, `POST /wip/counts`, `GET /wip/stations/{id}/total`, `PUT /wip/stations/{id}/status`, `GET /wip/stations/{id}/status`.
- Produces: default export `WipPanel`.

- [ ] **Step 1: Write `frontend/src/panels/WipPanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

const STATION_STATES = ['idle', 'running', 'down', 'blocked', 'setup'];

export default function WipPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [taskId, setTaskId] = useState(1);
  const [jobId, setJobId] = useState(1);
  const [stationId, setStationId] = useState(1);
  const [qty, setQty] = useState(1);
  const [lot, setLot] = useState('');

  const total = useApi<{ total: number }>(apiBase, `/wip/stations/${stationId}/total`, [stationId]);
  const stStatus = useApi<Record<string, unknown> | null>(apiBase, `/wip/stations/${stationId}/status`, [stationId]);

  const run = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    try { await fn(); after?.(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  return (
    <>
      <Section title="Job" actions={
        <>
          <Field label="Task id"><NumberInput value={taskId} onChange={setTaskId} /></Field>
          <Button onClick={() => run('Đã start job', () => api(apiBase, '/wip/jobs', { method: 'POST', body: JSON.stringify({ task_id: taskId, station_id: stationId }) }))}>Start</Button>
          <Field label="Job id"><NumberInput value={jobId} onChange={setJobId} /></Field>
          <Button variant="ghost" onClick={() => run('Đã complete job', () => api(apiBase, `/wip/jobs/${jobId}/complete`, { method: 'POST' }))}>Complete</Button>
        </>
      }>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <Field label="Lot / QR"><TextInput value={lot} onChange={setLot} placeholder="LOT-123" /></Field>
          <Button variant="ghost" onClick={() => run('Đã gắn lot', () => api(apiBase, `/wip/jobs/${jobId}/scan`, { method: 'POST', body: JSON.stringify({ code: lot }) }), () => setLot(''))}>Scan lot</Button>
        </div>
      </Section>

      <Section title={`Station ${stationId}`} actions={<Field label="Station"><NumberInput value={stationId} onChange={setStationId} /></Field>}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
          <Field label="Số lượng"><NumberInput value={qty} onChange={setQty} /></Field>
          <Button onClick={() => run('Đã ghi count', () => api(apiBase, '/wip/counts', { method: 'POST', body: JSON.stringify({ station_id: stationId, qty }) }), () => total.reload())}>+ Count</Button>
        </div>
        <p style={{ fontSize: 13 }}>Tổng sản lượng: <b>{total.data?.total ?? 0}</b> · Trạng thái: <b>{String(stStatus.data?.status ?? '—')}</b></p>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {STATION_STATES.map((s) => (
            <Button key={s} variant="ghost" onClick={() => run(`Station → ${s}`, () => api(apiBase, `/wip/stations/${stationId}/status`, { method: 'PUT', body: JSON.stringify({ status: s }) }), () => stStatus.reload())}>{s}</Button>
          ))}
        </div>
      </Section>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/WipPanel.tsx
git commit -m "feat(produce): WipPanel wired to /wip (E3)"
```

### Task 10: DowntimePanel (E4 — Operator log + Leader andon board)

**Files:**
- Replace: `frontend/src/panels/DowntimePanel.tsx`

**Interfaces:**
- Consumes: `POST /downtime/events`, `POST /downtime/events/{id}/close`, `GET /downtime/events/open`, `POST /downtime/andon`, `POST /downtime/andon/{id}/status`, `GET /downtime/andon/line/{line_id}`.
- Produces: default export `DowntimePanel` taking `{ apiBase, mode }` where `mode: 'log' | 'andon'` (default `'log'`).

- [ ] **Step 1: Write `frontend/src/panels/DowntimePanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function DowntimePanel({ apiBase, mode = 'log' }: { apiBase: string; mode?: 'log' | 'andon' }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [stationId, setStationId] = useState(1);
  const [category, setCategory] = useState('Mechanical');

  const open = useApi<Array<Record<string, unknown>>>(apiBase, '/downtime/events/open');
  const andons = useApi<Array<Record<string, unknown>>>(apiBase, `/downtime/andon/line/${lineId}`, [lineId]);

  const run = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    try { await fn(); after?.(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  if (mode === 'andon') {
    return (
      <Section title={`Andon · line ${lineId}`} actions={<Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>}>
        <DataTable
          columns={[
            { key: 'id', label: 'ID' }, { key: 'station_id', label: 'Station' }, { key: 'reason', label: 'Lý do' }, { key: 'status', label: 'Trạng thái' },
            { key: 'act', label: '', render: (r) => (
              <div style={{ display: 'flex', gap: 6 }}>
                <Button variant="ghost" onClick={() => run('Acknowledged', () => api(apiBase, `/downtime/andon/${r.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'acknowledged' }) }), () => andons.reload())}>Ack</Button>
                <Button variant="ghost" onClick={() => run('Resolved', () => api(apiBase, `/downtime/andon/${r.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'resolved' }) }), () => andons.reload())}>Resolve</Button>
              </div>
            ) },
          ]}
          rows={andons.data ?? []}
          empty="Không có andon đang mở"
        />
      </Section>
    );
  }

  return (
    <>
      <Section title="Ghi downtime" actions={
        <>
          <Field label="Station"><NumberInput value={stationId} onChange={setStationId} /></Field>
          <Field label="Category"><TextInput value={category} onChange={setCategory} /></Field>
          <Button onClick={() => run('Đã ghi downtime', () => api(apiBase, '/downtime/events', { method: 'POST', body: JSON.stringify({ station_id: stationId, category }) }), () => open.reload())}>Log</Button>
        </>
      }>
        <DataTable
          columns={[
            { key: 'id', label: 'ID' }, { key: 'station_id', label: 'Station' }, { key: 'category', label: 'Category' }, { key: 'started_at', label: 'Bắt đầu' },
            { key: 'act', label: '', render: (r) => <Button variant="ghost" onClick={() => run('Đã đóng', () => api(apiBase, `/downtime/events/${r.id}/close`, { method: 'POST' }), () => open.reload())}>Close</Button> },
          ]}
          rows={open.data ?? []}
          empty="Không có downtime mở"
        />
      </Section>
      <Section title="Andon" actions={<><Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field><Button variant="danger" onClick={() => run('Đã gọi andon', () => api(apiBase, '/downtime/andon', { method: 'POST', body: JSON.stringify({ line_id: lineId, station_id: stationId }) }))}>Gọi andon</Button></>}>
        <p style={{ fontSize: 13, color: '#888' }}>Gọi hỗ trợ khi không tự xử được (P-DOWN-02).</p>
      </Section>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/DowntimePanel.tsx
git commit -m "feat(produce): DowntimePanel log+andon wired to /downtime (E4)"
```

### Task 11: ScrapPanel (E5 — Operator scrap/rework + Supervisor hold)

**Files:**
- Replace: `frontend/src/panels/ScrapPanel.tsx`

**Interfaces:**
- Consumes: `POST /scrap/records`, `GET /scrap/total`, `POST /scrap/rework`, `POST /scrap/holds`, `POST /scrap/holds/{id}/release`, `GET /scrap/holds/active`.
- Produces: default export `ScrapPanel` taking `{ apiBase, mode }` where `mode: 'record' | 'hold'` (default `'record'`).

- [ ] **Step 1: Write `frontend/src/panels/ScrapPanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function ScrapPanel({ apiBase, mode = 'record' }: { apiBase: string; mode?: 'record' | 'hold' }) {
  const { notify } = useToast();
  const [shiftId, setShiftId] = useState(1);
  const [reason, setReason] = useState('D-01');
  const [qty, setQty] = useState(1);
  const [lot, setLot] = useState('');

  const total = useApi<{ total: number }>(apiBase, `/scrap/total?shift_id=${shiftId}`, [shiftId]);
  const holds = useApi<Array<Record<string, unknown>>>(apiBase, '/scrap/holds/active');

  const run = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    try { await fn(); after?.(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  if (mode === 'hold') {
    return (
      <Section title="Lot đang hold" actions={<><Field label="Lot"><TextInput value={lot} onChange={setLot} /></Field><Button variant="danger" onClick={() => run('Đã hold lot', () => api(apiBase, '/scrap/holds', { method: 'POST', body: JSON.stringify({ lot_code: lot }) }), () => { setLot(''); holds.reload(); })}>Hold</Button></>}>
        <DataTable
          columns={[
            { key: 'id', label: 'ID' }, { key: 'lot_code', label: 'Lot' }, { key: 'reason', label: 'Lý do' }, { key: 'held_at', label: 'Lúc' },
            { key: 'act', label: '', render: (r) => <Button variant="ghost" onClick={() => run('Đã release', () => api(apiBase, `/scrap/holds/${r.id}/release`, { method: 'POST' }), () => holds.reload())}>Release</Button> },
          ]}
          rows={holds.data ?? []}
          empty="Không có lot hold"
        />
      </Section>
    );
  }

  return (
    <>
      <Section title="Ghi phế phẩm" actions={
        <>
          <Field label="Shift"><NumberInput value={shiftId} onChange={setShiftId} /></Field>
          <Field label="Mã lỗi"><TextInput value={reason} onChange={setReason} /></Field>
          <Field label="SL"><NumberInput value={qty} onChange={setQty} /></Field>
          <Button onClick={() => run('Đã ghi phế phẩm', () => api(apiBase, '/scrap/records', { method: 'POST', body: JSON.stringify({ reason_code: reason, qty, shift_id: shiftId }) }), () => total.reload())}>Ghi</Button>
        </>
      }>
        <p style={{ fontSize: 13 }}>Tổng phế phẩm ca {shiftId}: <b>{total.data?.total ?? 0}</b></p>
      </Section>
      <Section title="Rework" actions={<><Field label="Lot"><TextInput value={lot} onChange={setLot} /></Field><Button variant="ghost" onClick={() => run('Đã đánh dấu rework', () => api(apiBase, '/scrap/rework', { method: 'POST', body: JSON.stringify({ lot_code: lot }) }), () => setLot(''))}>Đánh dấu rework</Button></>}>
        <p style={{ fontSize: 13, color: '#888' }}>Đưa lot vào luồng rework (P-SCRAP-02).</p>
      </Section>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/ScrapPanel.tsx
git commit -m "feat(produce): ScrapPanel record+hold wired to /scrap (E5)"
```

### Task 12: ExceptionPanel (E9 — Leader triage + Supervisor escalated)

**Files:**
- Replace: `frontend/src/panels/ExceptionPanel.tsx`

**Interfaces:**
- Consumes: `POST /exception/exceptions`, `GET /exception/line/{line_id}/open`, `GET /exception/escalated`, `POST /exception/exceptions/{id}/triage`, `POST /exception/exceptions/{id}/escalate`, `POST /exception/exceptions/{id}/resolve`.
- Produces: default export `ExceptionPanel` taking `{ apiBase, mode }` where `mode: 'triage' | 'escalated'` (default `'triage'`).

- [ ] **Step 1: Write `frontend/src/panels/ExceptionPanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function ExceptionPanel({ apiBase, mode = 'triage' }: { apiBase: string; mode?: 'triage' | 'escalated' }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [reason, setReason] = useState('thiếu vật tư');

  const open = useApi<Array<Record<string, unknown>>>(apiBase, `/exception/line/${lineId}/open`, [lineId]);
  const escalated = useApi<Array<Record<string, unknown>>>(apiBase, '/exception/escalated');
  const active = mode === 'escalated' ? escalated : open;

  const run = async (label: string, fn: () => Promise<unknown>) => {
    try { await fn(); active.reload(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const cols = [
    { key: 'id', label: 'ID' }, { key: 'reason', label: 'Lý do' }, { key: 'category', label: 'Loại' }, { key: 'status', label: 'Trạng thái' }, { key: 'opened_at', label: 'Mở lúc' },
    { key: 'act', label: '', render: (r: Record<string, unknown>) => (
      <div style={{ display: 'flex', gap: 6 }}>
        {mode === 'triage' && <Button variant="ghost" onClick={() => run('Đã phân loại', () => api(apiBase, `/exception/exceptions/${r.id}/triage`, { method: 'POST', body: JSON.stringify({ category: 'material' }) }))}>Triage</Button>}
        {mode === 'triage' && <Button variant="ghost" onClick={() => run('Đã escalate', () => api(apiBase, `/exception/exceptions/${r.id}/escalate`, { method: 'POST' }))}>Escalate</Button>}
        <Button variant="ghost" onClick={() => run('Đã đóng', () => api(apiBase, `/exception/exceptions/${r.id}/resolve`, { method: 'POST' }))}>Resolve</Button>
      </div>
    ) },
  ];

  return (
    <Section
      title={mode === 'escalated' ? 'Ngoại lệ đã escalate' : `Ngoại lệ mở · line ${lineId}`}
      actions={mode === 'triage'
        ? <><Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field><Field label="Lý do"><TextInput value={reason} onChange={setReason} /></Field><Button onClick={() => run('Đã raise', () => api(apiBase, '/exception/exceptions', { method: 'POST', body: JSON.stringify({ line_id: lineId, reason }) }))}>Raise</Button></>
        : undefined}
    >
      <DataTable columns={cols} rows={active.data ?? []} empty="Không có ngoại lệ" />
    </Section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/ExceptionPanel.tsx
git commit -m "feat(produce): ExceptionPanel triage+escalated wired to /exception (E9)"
```

### Task 13: SetupPanel (E7 — Admin/Operator changeover)

**Files:**
- Replace: `frontend/src/panels/SetupPanel.tsx`

**Interfaces:**
- Consumes: `POST /setup/changeovers`, `POST /setup/changeovers/{id}/complete`, `POST /setup/changeovers/{id}/first-piece`, `GET /setup/line/{line_id}/open`.
- Produces: default export `SetupPanel`.

- [ ] **Step 1: Write `frontend/src/panels/SetupPanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function SetupPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [toPart, setToPart] = useState(1);

  const open = useApi<Array<Record<string, unknown>>>(apiBase, `/setup/line/${lineId}/open`, [lineId]);
  const run = async (label: string, fn: () => Promise<unknown>) => {
    try { await fn(); open.reload(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const start = () => run('Đã bắt đầu changeover', () => api(apiBase, '/setup/changeovers', { method: 'POST', body: JSON.stringify({ line_id: lineId, to_part_id: toPart, checklist: [{ name: 'thay khuôn', done: false }, { name: 'chỉnh cữ', done: false }] }) }));

  return (
    <Section title={`Changeover · line ${lineId}`} actions={
      <>
        <Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>
        <Field label="Part mới"><NumberInput value={toPart} onChange={setToPart} /></Field>
        <Button onClick={start}>Bắt đầu</Button>
      </>
    }>
      <DataTable
        columns={[
          { key: 'id', label: 'ID' }, { key: 'to_part_id', label: 'Part mới' }, { key: 'started_at', label: 'Bắt đầu' },
          { key: 'act', label: '', render: (r) => (
            <div style={{ display: 'flex', gap: 6 }}>
              <Button variant="ghost" onClick={() => run('Đã hoàn tất', () => api(apiBase, `/setup/changeovers/${r.id}/complete`, { method: 'POST' }))}>Complete</Button>
              <Button variant="ghost" onClick={() => run('First-piece đạt', () => api(apiBase, `/setup/changeovers/${r.id}/first-piece`, { method: 'POST', body: JSON.stringify({ passed: true }) }))}>First-piece ✓</Button>
            </div>
          ) },
        ]}
        rows={open.data ?? []}
        empty="Không có changeover mở"
      />
    </Section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/SetupPanel.tsx
git commit -m "feat(produce): SetupPanel wired to /setup (E7)"
```

### Task 14: OeePanel (E6 — Admin load order + Supervisor read)

**Files:**
- Replace: `frontend/src/panels/OeePanel.tsx`

**Interfaces:**
- Consumes: `POST /oee/production-orders`, `GET /oee/shifts/{shift_id}?total_count=N`.
- Produces: default export `OeePanel`.

- [ ] **Step 1: Write `frontend/src/panels/OeePanel.tsx`**

```tsx
import { useState } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function OeePanel({ apiBase }: { apiBase: string }) {
  const { tokens } = useMinderTheme();
  const { notify } = useToast();
  const [shiftId, setShiftId] = useState(1);
  const [lineId, setLineId] = useState(1);
  const [ict, setIct] = useState(60);
  const [target, setTarget] = useState(500);
  const [planned, setPlanned] = useState(480);
  const [totalCount, setTotalCount] = useState(400);

  const oee = useApi<Record<string, number> & { error?: string }>(apiBase, `/oee/shifts/${shiftId}?total_count=${totalCount}`, [shiftId, totalCount]);

  const load = async () => {
    try {
      await api(apiBase, '/oee/production-orders', { method: 'POST', body: JSON.stringify({ line_id: lineId, shift_id: shiftId, ideal_cycle_time: ict, target_count: target, planned_minutes: planned }) });
      oee.reload(); notify('Đã nạp production order');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const gauge = (label: string, v: number | undefined) => (
    <div style={{ flex: 1, background: tokens.surfaceAlt, borderRadius: 10, padding: 14, textAlign: 'center' }}>
      <div style={{ fontSize: 12, color: tokens.textMuted }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: tokens.text }}>{v === undefined ? '—' : `${Math.round(v * 100)}%`}</div>
    </div>
  );

  return (
    <>
      <Section title="Nạp production order (chuẩn ca)" actions={<Button onClick={load}>Nạp</Button>}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>
          <Field label="Shift"><NumberInput value={shiftId} onChange={setShiftId} /></Field>
          <Field label="Ideal cycle (s)"><NumberInput value={ict} onChange={setIct} /></Field>
          <Field label="Target"><NumberInput value={target} onChange={setTarget} /></Field>
          <Field label="Planned (phút)"><NumberInput value={planned} onChange={setPlanned} /></Field>
        </div>
      </Section>

      <Section title={`OEE ca ${shiftId}`} actions={<Field label="Sản lượng ca"><NumberInput value={totalCount} onChange={setTotalCount} /></Field>}>
        {oee.data?.error ? (
          <p style={{ color: tokens.warning, fontSize: 13 }}>{oee.data.error}</p>
        ) : (
          <div style={{ display: 'flex', gap: 10 }}>
            {gauge('Availability', oee.data?.availability)}
            {gauge('Performance', oee.data?.performance)}
            {gauge('Quality', oee.data?.quality)}
            {gauge('OEE', oee.data?.oee)}
          </div>
        )}
      </Section>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/OeePanel.tsx
git commit -m "feat(produce): OeePanel load-order + A/P/Q gauges wired to /oee (E6)"
```

### Task 15: HandoverPanel (E8 — Supervisor)

**Files:**
- Replace: `frontend/src/panels/HandoverPanel.tsx`

**Interfaces:**
- Consumes: `POST /handover/records`, `GET /handover/shifts/{from_shift_id}`, `POST /handover/records/{id}/acknowledge`.
- Produces: default export `HandoverPanel`.

- [ ] **Step 1: Write `frontend/src/panels/HandoverPanel.tsx`**

```tsx
import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function HandoverPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [fromShift, setFromShift] = useState(1);
  const [output, setOutput] = useState(0);

  const current = useApi<Record<string, unknown> | null>(apiBase, `/handover/shifts/${fromShift}`, [fromShift]);
  const run = async (label: string, fn: () => Promise<unknown>) => {
    try { await fn(); current.reload(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const create = () => run('Đã tạo bàn giao', () => api(apiBase, '/handover/records', { method: 'POST', body: JSON.stringify({ line_id: lineId, from_shift_id: fromShift, output_count: output }) }));
  const h = current.data;

  return (
    <Section title="Bàn giao ca" actions={
      <>
        <Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>
        <Field label="Ca ra"><NumberInput value={fromShift} onChange={setFromShift} /></Field>
        <Field label="Sản lượng"><NumberInput value={output} onChange={setOutput} /></Field>
        <Button onClick={create}>Tạo</Button>
      </>
    }>
      {h ? (
        <div style={{ fontSize: 13, lineHeight: 1.8 }}>
          <div>Sản lượng: <b>{String(h.output_count)}</b></div>
          <div>Việc treo: <b>{(h.pending as unknown[])?.length ?? 0}</b> · Downtime mở: <b>{(h.open_downtime as unknown[])?.length ?? 0}</b></div>
          <div>Đã đọc: <b>{h.acknowledged_at ? String(h.acknowledged_at) : 'chưa'}</b></div>
          {!h.acknowledged_at && <Button onClick={() => run('Đã xác nhận đọc', () => api(apiBase, `/handover/records/${h.id}/acknowledge`, { method: 'POST' }))}>Xác nhận đã đọc</Button>}
        </div>
      ) : <p style={{ fontSize: 13, color: '#888' }}>Chưa có bàn giao cho ca này.</p>}
    </Section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/HandoverPanel.tsx
git commit -m "feat(produce): HandoverPanel wired to /handover (E8)"
```

### Task 16: ReportPanel (E10 — Manager live + end-of-shift)

**Files:**
- Replace: `frontend/src/panels/ReportPanel.tsx`

**Interfaces:**
- Consumes: `GET /report/live/{line_id}`, `GET /report/end-of-shift?line_id=&shift_id=&total_count=`.
- Produces: default export `ReportPanel`.

- [ ] **Step 1: Write `frontend/src/panels/ReportPanel.tsx`**

```tsx
import { useState } from 'react';
import { useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import { Field, NumberInput } from '../ui/Field';

export default function ReportPanel({ apiBase }: { apiBase: string }) {
  const [lineId, setLineId] = useState(1);
  const [shiftId, setShiftId] = useState(1);
  const [totalCount, setTotalCount] = useState(300);

  const live = useApi<{ tasks: unknown[]; open_andons: unknown[]; open_exceptions: unknown[] }>(apiBase, `/report/live/${lineId}`, [lineId]);
  const eos = useApi<Record<string, unknown>>(apiBase, `/report/end-of-shift?line_id=${lineId}&shift_id=${shiftId}&total_count=${totalCount}`, [lineId, shiftId, totalCount]);

  return (
    <>
      <Section title="Dashboard live" actions={<Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>}>
        <div style={{ display: 'flex', gap: 24, fontSize: 13 }}>
          <div>Task: <b>{live.data?.tasks.length ?? 0}</b></div>
          <div>Andon mở: <b>{live.data?.open_andons.length ?? 0}</b></div>
          <div>Ngoại lệ mở: <b>{live.data?.open_exceptions.length ?? 0}</b></div>
        </div>
      </Section>

      <Section title="Báo cáo cuối ca" actions={<><Field label="Shift"><NumberInput value={shiftId} onChange={setShiftId} /></Field><Field label="Sản lượng"><NumberInput value={totalCount} onChange={setTotalCount} /></Field></>}>
        <div style={{ fontSize: 13, marginBottom: 12 }}>
          Sản lượng: <b>{String(eos.data?.output_count ?? 0)}</b> · Phế phẩm: <b>{String(eos.data?.scrap_count ?? 0)}</b> ·
          OEE: <b>{(eos.data?.oee as Record<string, unknown>)?.oee !== undefined ? String((eos.data?.oee as Record<string, unknown>).oee) : '—'}</b>
        </div>
        <DataTable columns={[{ key: 'category', label: 'Lý do downtime' }, { key: 'count', label: 'Số lần' }]} rows={(eos.data?.top_downtime_reasons as Array<Record<string, unknown>>) ?? []} empty="Không có downtime" />
      </Section>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add modules/produce/frontend/src/panels/ReportPanel.tsx
git commit -m "feat(produce): ReportPanel live+end-of-shift wired to /report (E10)"
```

---

## Phase 4 — Persona routes (compose panels) + build gate

### Task 17: Persona route components

**Files:**
- Replace: `frontend/src/routes/operator.tsx`, `frontend/src/routes/leader.tsx`, `frontend/src/routes/supervisor.tsx`, `frontend/src/routes/manager.tsx`, `frontend/src/routes/admin.tsx`

**Interfaces:**
- Consumes: the 11 panels (default exports) with their `mode` props defined above.
- Produces: 5 default-export route components taking `{ apiBase }`.

- [ ] **Step 1: Write `frontend/src/routes/operator.tsx`**

```tsx
import WorkPanel from '../panels/WorkPanel';
import SopPanel from '../panels/SopPanel';
import WipPanel from '../panels/WipPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ScrapPanel from '../panels/ScrapPanel';

export default function OperatorRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <WorkPanel apiBase={apiBase} mode="queue" />
      <SopPanel apiBase={apiBase} />
      <WipPanel apiBase={apiBase} />
      <DowntimePanel apiBase={apiBase} mode="log" />
      <ScrapPanel apiBase={apiBase} mode="record" />
    </>
  );
}
```

- [ ] **Step 2: Write `frontend/src/routes/leader.tsx`**

```tsx
import WorkPanel from '../panels/WorkPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ExceptionPanel from '../panels/ExceptionPanel';

export default function LeaderRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <WorkPanel apiBase={apiBase} mode="board" />
      <DowntimePanel apiBase={apiBase} mode="andon" />
      <ExceptionPanel apiBase={apiBase} mode="triage" />
    </>
  );
}
```

- [ ] **Step 3: Write `frontend/src/routes/supervisor.tsx`**

```tsx
import OeePanel from '../panels/OeePanel';
import HandoverPanel from '../panels/HandoverPanel';
import ScrapPanel from '../panels/ScrapPanel';
import ExceptionPanel from '../panels/ExceptionPanel';

export default function SupervisorRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <OeePanel apiBase={apiBase} />
      <HandoverPanel apiBase={apiBase} />
      <ScrapPanel apiBase={apiBase} mode="hold" />
      <ExceptionPanel apiBase={apiBase} mode="escalated" />
    </>
  );
}
```

- [ ] **Step 4: Write `frontend/src/routes/manager.tsx`**

```tsx
import ReportPanel from '../panels/ReportPanel';

export default function ManagerRoute({ apiBase }: { apiBase: string }) {
  return <ReportPanel apiBase={apiBase} />;
}
```

- [ ] **Step 5: Write `frontend/src/routes/admin.tsx`**

```tsx
import ConfigPanel from '../panels/ConfigPanel';
import SopPanel from '../panels/SopPanel';
import SetupPanel from '../panels/SetupPanel';
import OeePanel from '../panels/OeePanel';

export default function AdminRoute({ apiBase }: { apiBase: string }) {
  return (
    <>
      <ConfigPanel apiBase={apiBase} />
      <SopPanel apiBase={apiBase} />
      <SetupPanel apiBase={apiBase} />
      <OeePanel apiBase={apiBase} />
    </>
  );
}
```

- [ ] **Step 6: Full build gate**

Run: `cd modules/produce/frontend && npm run build`
Expected: build SUCCEEDS; `dist/index.html`, `dist/remoteEntry.js`, and `dist/assets/*` emitted; no TS errors. If a panel prop mismatch surfaces (e.g. a `mode` value), fix inline and rebuild.

- [ ] **Step 7: Commit**

```bash
cd /Users/anlnm/Desktop/Project/opendev-py
git add modules/produce/frontend/src/routes
git commit -m "feat(produce): persona routes compose epic panels; frontend builds"
```

---

## Phase 5 — Deployment

### Task 18: Backend Dockerfile (multi-stage: frontend build → python)

**Files:**
- Create: `modules/produce/backend/Dockerfile`

**Interfaces:**
- Produces: image running `uvicorn app:app` on `9310` with `frontend_dist/` populated so the SPA serves at `/`.

- [ ] **Step 1: Create `modules/produce/backend/Dockerfile`**

```dockerfile
# Build context is the REPO ROOT (shared minder_ui_sdk lives outside the module).

# --- frontend build stage ---
FROM node:20-slim AS fe
WORKDIR /fe
COPY modules/produce/frontend/package.json modules/produce/frontend/package-lock.json* ./
RUN npm install
COPY modules/produce/frontend/ ./
COPY minder_ui_sdk /minder_ui_sdk
ARG PR_PUBLIC_BASE=http://localhost:9310
ENV PR_PUBLIC_BASE=$PR_PUBLIC_BASE
RUN npm run build

# --- python service stage ---
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY modules/produce/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/produce/backend/ /app
COPY --from=fe /fe/dist /app/frontend_dist
ENV PYTHONUNBUFFERED=1
RUN useradd --system --create-home appuser
USER appuser
EXPOSE 9310
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9310"]
```

- [ ] **Step 2: Verify it builds** (from repo root)

Run: `docker build -f modules/produce/backend/Dockerfile -t produce-web .`
Expected: build SUCCEEDS through both stages.

- [ ] **Step 3: Commit**

```bash
git add modules/produce/backend/Dockerfile
git commit -m "feat(produce): backend Dockerfile (fe build + uvicorn on 9310)"
```

### Task 19: Celery app + worker + worker Dockerfile

**Files:**
- Create: `modules/produce/backend/celery_app.py`
- Replace: `modules/produce/worker/tasks.py`
- Create: `modules/produce/worker/Dockerfile`
- Test: `modules/produce/backend/tests/test_worker.py`

**Interfaces:**
- Consumes: `domain.oee.service.shift_oee` (existing).
- Produces: `celery_app` (Celery), task `oee_snapshot(shift_id, total_count) -> dict` importable as `tasks.oee_snapshot`. In eager test mode (`PR_TEST=1`) the task runs inline.

- [ ] **Step 1: Write the failing test** — create `modules/produce/backend/tests/test_worker.py`:

```python
"""Worker task smoke test (eager) — in-memory SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_oee_snapshot_task_runs_eager():
    from domain.oee import service
    import tasks

    service.load_production_order(
        line_id=1, shift_id=1, ideal_cycle_time=60, target_count=500, planned_minutes=480
    )
    result = tasks.oee_snapshot.apply(args=(1, 400)).get()
    assert result["shift_id"] == 1
    assert 0.0 <= result["oee"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PR_TEST=1 uv run --no-sync pytest tests/test_worker.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tasks'` — backend has no `tasks.py`).

- [ ] **Step 3: Create `modules/produce/backend/celery_app.py`**

```python
"""Produce Celery app — reuses the shared Redis INSTANCE at DB index /3."""

from __future__ import annotations

import os

from celery import Celery

PR_REDIS_URL = os.environ.get("PR_REDIS_URL", "redis://redis:6379/3")

celery_app = Celery("produce", broker=PR_REDIS_URL, backend=PR_REDIS_URL, include=["tasks"])
celery_app.conf.update(task_track_started=True, result_expires=3600)
if os.environ.get("PR_TEST") == "1":
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
```

- [ ] **Step 4: Create `modules/produce/backend/tasks.py`**

```python
"""Produce Celery tasks (Track A). Periodic OEE snapshotting — pure roll-up over
the module's own data; never imports minder."""

from __future__ import annotations

from celery_app import celery_app
from domain.oee import service as oee_service


@celery_app.task(name="produce.oee_snapshot")
def oee_snapshot(shift_id: int, total_count: int) -> dict:
    """Compute and return the current OEE snapshot for a shift (P-OEE-03 backend)."""
    return oee_service.shift_oee(shift_id, total_count)
```

Note: the worker container runs `celery -A tasks worker`; `worker/tasks.py` just re-exports so both `backend/` and `worker/` code trees resolve `tasks`.

- [ ] **Step 5: Replace `modules/produce/worker/tasks.py`**

```python
"""Produce worker entrypoint — imports the backend task module so `celery -A tasks`
resolves. The worker Dockerfile sets WORKDIR to the backend code tree, so this
file is only used when running the worker from the module root."""

from __future__ import annotations

from celery_app import celery_app  # noqa: F401
from tasks import oee_snapshot  # noqa: F401
```

- [ ] **Step 6: Create `modules/produce/worker/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY modules/produce/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY modules/produce/backend/ /app
ENV PYTHONUNBUFFERED=1
RUN useradd --system --create-home appuser
USER appuser
CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `PR_TEST=1 uv run --no-sync pytest tests/test_worker.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add modules/produce/backend/celery_app.py modules/produce/backend/tasks.py modules/produce/worker/tasks.py modules/produce/worker/Dockerfile
git add -f modules/produce/backend/tests/test_worker.py
git commit -m "feat(produce): Celery app + oee_snapshot task + worker Dockerfile"
```

### Task 20: Compose snippet + README

**Files:**
- Create: `modules/produce/docker-compose.snippet.yml`, `modules/produce/README.md`

**Interfaces:**
- Produces: paste-in compose services `produce-web` (9310) + `produce-worker`; README documents run + architecture.

- [ ] **Step 1: Create `modules/produce/docker-compose.snippet.yml`**

```yaml
# Paste into docker-compose.yml (same network as `minder`). Build context = repo root.
# Track A is standalone: no MinIO, no Keycloak, no Minder connector env — pure software.

  produce-web:
    build: { context: ., dockerfile: modules/produce/backend/Dockerfile }
    ports: ["9310:9310"]
    depends_on: [db, redis]
    environment:
      PR_DATABASE_URL: "postgresql://minder:minder@db:5432/minder"
      PR_REDIS_URL: "redis://redis:6379/3"
      PR_PUBLIC_BASE: "http://localhost:9310"

  produce-worker:
    build: { context: ., dockerfile: modules/produce/worker/Dockerfile }
    depends_on: [db, redis]
    environment:
      PR_DATABASE_URL: "postgresql://minder:minder@db:5432/minder"
      PR_REDIS_URL: "redis://redis:6379/3"
```

- [ ] **Step 2: Create `modules/produce/README.md`**

```markdown
# produce — MES Track A (phần mềm thuần)

Standalone Manufacturing Execution System. Human-operated; **no Minder / no AI**
(Track B SDK layers on later without touching this code). Built from
`Minder_Produce_Backlog_Roadmap` (Part 1).

## Epics → REST prefix
E11 Config `/config` · E1 Work `/work` · E2 SOP `/sop` · E3 WIP `/wip` ·
E4 Downtime `/downtime` · E5 Scrap `/scrap` · E6 OEE `/oee` · E7 Setup `/setup` ·
E8 Handover `/handover` · E9 Exception `/exception` · E10 Report `/report`.

## UI
Hybrid: 5 persona tabs (Operator / Tổ trưởng / Quản ca / Quản lý xưởng / FDE-Admin)
→ epic panels inside each. React + Vite; served standalone by the backend at `/`.

## Architecture
- Backend: FastAPI, one router per epic, `pr_*` tables on shared Postgres
  (`PR_DATABASE_URL`), lazy engine. Serves the built UI from `frontend_dist/`.
- Worker: Celery on `PR_REDIS_URL` (Redis DB `/3`) — `oee_snapshot` roll-up.
- Data isolation: creates/owns `pr_*` tables only; never writes Minder tables.

## Run
- Local dev: backend `uvicorn app:app --port 9310` (from `backend/`), frontend
  `npm run dev` (vite on 5173, talks to 9310 via CORS).
- Docker: paste `docker-compose.snippet.yml` into `docker-compose.yml`, then
  `docker compose up -d --build produce-web produce-worker`. UI at
  `http://localhost:9310/`.

## Test
From `backend/`: `uv run --no-sync pytest` (SQLite in-memory; no Postgres needed).
```

- [ ] **Step 3: Commit**

```bash
git add modules/produce/docker-compose.snippet.yml modules/produce/README.md
git commit -m "docs(produce): compose snippet + README for Track A"
```

### Task 21: Full regression + integration note

**Files:**
- Modify: `modules/module_integration.md` (append a Produce entry)

- [ ] **Step 1: Run the whole backend suite**

Run: `cd modules/produce/backend && PR_TEST=1 uv run --no-sync pytest -q && cd /Users/anlnm/Desktop/Project/opendev-py && uv run --no-sync ruff check modules/produce/backend`
Expected: all tests PASS (30+), ruff "All checks passed!".

- [ ] **Step 2: Append a Produce section to `modules/module_integration.md`** documenting: module id `produce`, port `9310`, env `PR_DATABASE_URL` / `PR_REDIS_URL` / `PR_PUBLIC_BASE`, table prefix `pr_`, Track A only (no connector/Keycloak/MinIO). Follow the heading style already used in that file for module_template.

- [ ] **Step 3: Commit**

```bash
git add modules/module_integration.md
git commit -m "docs(produce): register Produce module in integration guide"
```

---

## Self-Review

**Spec coverage (Part 1 epics):** E1 → Task 8; E2 → Task 7; E3 → Task 9; E4 → Task 10; E5 → Task 11; E6 → Task 14; E7 → Task 13; E8 → Task 15; E9 → Task 12; E10 → Task 16; E11 → Task 6 (+ Task 2 threshold/skill). UI shell → Task 5; personas → Task 17; backend serving → Task 1; deployment → Tasks 18-20; regression → Task 21. Track B (Part 2 SDK) intentionally OUT of scope per user ("build Track A trước").

**Placeholder scan:** every code step contains complete files/functions; no "TODO"/"handle edge cases"/"similar to Task N". Error handling is concrete (try/catch → `notify(msg,'err')`; backend 409 → thrown `Error(detail)`).

**Type consistency:** `api(base,path,init?)` and `useApi(base,path,deps?)` signatures used identically across all panels. `DataTable` `Column<T>` `{key,label,render?}` consistent. Panel `mode` unions: WorkPanel `'queue'|'board'`, DowntimePanel `'log'|'andon'`, ScrapPanel `'record'|'hold'`, ExceptionPanel `'triage'|'escalated'` — each route passes only declared values. `oee_snapshot(shift_id,total_count)` matches `shift_oee` signature.

**Known follow-ups (not blockers, out of MVP scope):** non-MVP stories (P-EXEC-05 diff-from-last-shift, P-WIP-04/05 batch/WIP-per-station views, P-OEE-04/05 loss breakdown, P-RPT-03/04/05 trends & floor display, P-DOWN-04/06 threshold alerts & reason library UI) remain backend-absent or UI-absent; add as a later plan.
