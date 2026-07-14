# minder_ui_sdk — Tabs (host header driven) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép một module federation khai báo tabs một lần trong TS; tabs đó
đẩy lên host top-bar và điều khiển panel nào render (host → module một chiều).

**Architecture:** Package TS mới `minder_ui_sdk/` export `defineDashboard()`
(shell render panel theo `activeTab`) và vite plugin `minderTabsSync()` (đọc
`src/dashboard.tabs.ts` data thuần → merge `dashboard.tabs` vào `manifest.json`
lúc build). Host web-ui truyền `activeTab` xuống federated component. Module
`module_template` và scaffolder `service` dùng SDK.

**Tech Stack:** TypeScript, React 18, Vite 5, `@module-federation/vite`, esbuild
(có sẵn trong vite), vitest + @testing-library/react, Python (scaffolder +
pytest).

## Global Constraints

- Node/React: `react@^18.3.1`, `react-dom@^18.3.1` (federation singleton).
- Vite: `^5.1.4`; `@module-federation/vite@^1.16.14`.
- Line length Python 100 ký tự; Google-style docstrings; mypy strict cho public API.
- Không commit runtime data; spec/plan force-add vào `docs/` (đang gitignore).
- Không thêm trailer `Co-Authored-By: Claude` vào commit.
- Manifest ghi bằng `JSON.stringify(obj, null, 2) + "\n"` (khớp style scaffolder).
- SDK consume qua vite `resolve.alias` + tsconfig `paths` (KHÔNG build SDK, KHÔNG
  npm file: dep). Plugin import trong `vite.config.ts` bằng đường dẫn tương đối.
- SDK là source-only; `component`/`header` là passthrough, `icon` chỉ là metadata
  (host render label-only, không render icon).

---

### Task 1: `defineDashboard` + types (package `minder_ui_sdk`)

**Files:**
- Create: `minder_ui_sdk/package.json`
- Create: `minder_ui_sdk/tsconfig.json`
- Create: `minder_ui_sdk/vitest.config.ts`
- Create: `minder_ui_sdk/src/types.ts`
- Create: `minder_ui_sdk/src/defineDashboard.tsx`
- Create: `minder_ui_sdk/src/index.ts`
- Test: `minder_ui_sdk/tests/defineDashboard.test.tsx`

**Interfaces:**
- Produces:
  - `interface TabMeta { id: string; label: string; icon?: string }`
  - `interface DashboardProps { apiBase: string; activeTab?: string | null }`
  - `interface DashboardConfig { title?: string; header?: ComponentType<{ apiBase: string }>; tabs: TabMeta[]; panels: Record<string, ComponentType<{ apiBase: string }>> }`
  - `type DashboardComponent = FC<DashboardProps> & { meta: { title?: string; tabs: TabMeta[] } }`
  - `defineDashboard(config: DashboardConfig): DashboardComponent`

- [ ] **Step 1: Tạo `minder_ui_sdk/package.json`**

```json
{
  "name": "minder-ui-sdk",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": {
    ".": "./src/index.ts",
    "./vite": "./src/vitePlugin.ts"
  },
  "scripts": {
    "test": "vitest run"
  },
  "peerDependencies": {
    "react": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/react": "^16.3.2",
    "@types/react": "^18.3.1",
    "esbuild": "^0.21.5",
    "jsdom": "^24.1.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "typescript": "^5.4.0",
    "vitest": "^1.6.1"
  }
}
```

- [ ] **Step 2: Tạo `minder_ui_sdk/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "esnext",
    "module": "esnext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "types": ["vitest/globals"]
  },
  "include": ["src", "tests"]
}
```

- [ ] **Step 3: Tạo `minder_ui_sdk/vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
  },
});
```

- [ ] **Step 4: Tạo `minder_ui_sdk/src/types.ts`**

```ts
import type { ComponentType } from 'react';

/** Tab metadata — plain, JSON-serializable (id/label go to the host manifest). */
export interface TabMeta {
  id: string;
  label: string;
  icon?: string;
}

/** Props the Minder host passes to a module's federated `./Dashboard`. */
export interface DashboardProps {
  apiBase: string;
  activeTab?: string | null;
}

export interface DashboardConfig {
  title?: string;
  /** Persistent chrome above the active panel (stat cards, health, …). */
  header?: ComponentType<{ apiBase: string }>;
  /** Tab metadata — the single source of truth for tab identity/labels. */
  tabs: TabMeta[];
  /** Panel component per tab id. Keys must cover every tab id. */
  panels: Record<string, ComponentType<{ apiBase: string }>>;
}

export type DashboardComponent = ComponentType<DashboardProps> & {
  meta: { title?: string; tabs: TabMeta[] };
};
```

- [ ] **Step 5: Viết test thất bại `minder_ui_sdk/tests/defineDashboard.test.tsx`**

```tsx
import { render, screen } from '@testing-library/react';
import { defineDashboard } from '../src/defineDashboard';

const Header = ({ apiBase }: { apiBase: string }) => <div>hdr:{apiBase}</div>;
const Jobs = ({ apiBase }: { apiBase: string }) => <div>jobs:{apiBase}</div>;
const Media = ({ apiBase }: { apiBase: string }) => <div>media:{apiBase}</div>;

const Dash = defineDashboard({
  title: 'T',
  header: Header,
  tabs: [
    { id: 'jobs', label: 'Jobs' },
    { id: 'media', label: 'Media' },
  ],
  panels: { jobs: Jobs, media: Media },
});

it('renders the panel for the active tab', () => {
  render(<Dash apiBase="/api" activeTab="media" />);
  expect(screen.getByText('media:/api')).toBeTruthy();
});

it('falls back to the first tab when activeTab is null or unknown', () => {
  const { rerender } = render(<Dash apiBase="/api" activeTab={null} />);
  expect(screen.getByText('jobs:/api')).toBeTruthy();
  rerender(<Dash apiBase="/api" activeTab="nope" />);
  expect(screen.getByText('jobs:/api')).toBeTruthy();
});

it('renders the persistent header slot', () => {
  render(<Dash apiBase="/api" activeTab="jobs" />);
  expect(screen.getByText('hdr:/api')).toBeTruthy();
});

it('exposes meta.tabs as {id,label}', () => {
  expect(Dash.meta.tabs).toEqual([
    { id: 'jobs', label: 'Jobs', icon: undefined },
    { id: 'media', label: 'Media', icon: undefined },
  ]);
});
```

- [ ] **Step 6: Chạy test — kỳ vọng FAIL**

Run: `cd minder_ui_sdk && npm install && npm test`
Expected: FAIL — `Cannot find module '../src/defineDashboard'`.

- [ ] **Step 7: Viết `minder_ui_sdk/src/defineDashboard.tsx`**

```tsx
import type { ReactElement } from 'react';
import type { DashboardComponent, DashboardConfig, DashboardProps } from './types';

/**
 * Build a module's federated `./Dashboard` from a tab config. The host owns the
 * tab row (top bar) and passes `activeTab` down; this shell renders the matching
 * panel (falling back to the first tab) plus an optional persistent header.
 */
export function defineDashboard(config: DashboardConfig): DashboardComponent {
  const firstId = config.tabs[0]?.id ?? null;

  function Dashboard({ apiBase, activeTab }: DashboardProps): ReactElement {
    const id = activeTab && config.panels[activeTab] ? activeTab : firstId;
    const Panel = id ? config.panels[id] : undefined;
    const Header = config.header;
    return (
      <div data-minder-dashboard="">
        {Header ? <Header apiBase={apiBase} /> : null}
        {Panel ? <Panel apiBase={apiBase} /> : null}
      </div>
    );
  }

  const withMeta = Dashboard as DashboardComponent;
  withMeta.meta = {
    title: config.title,
    tabs: config.tabs.map((t) => ({ id: t.id, label: t.label, icon: t.icon })),
  };
  return withMeta;
}
```

- [ ] **Step 8: Viết `minder_ui_sdk/src/index.ts`**

```ts
export { defineDashboard } from './defineDashboard';
export type {
  TabMeta,
  DashboardProps,
  DashboardConfig,
  DashboardComponent,
} from './types';
```

- [ ] **Step 9: Chạy test — kỳ vọng PASS**

Run: `cd minder_ui_sdk && npm test`
Expected: PASS (4 tests).

- [ ] **Step 10: Commit**

```bash
git add minder_ui_sdk/package.json minder_ui_sdk/tsconfig.json \
  minder_ui_sdk/vitest.config.ts minder_ui_sdk/src/types.ts \
  minder_ui_sdk/src/defineDashboard.tsx minder_ui_sdk/src/index.ts \
  minder_ui_sdk/tests/defineDashboard.test.tsx
git commit -m "feat(ui-sdk): defineDashboard shell for host-driven module tabs"
```

---

### Task 2: `minderTabsSync` vite plugin + manifest merge

**Files:**
- Create: `minder_ui_sdk/src/manifestSync.ts`
- Create: `minder_ui_sdk/src/vitePlugin.ts`
- Test: `minder_ui_sdk/tests/manifestSync.test.ts`

**Interfaces:**
- Consumes: `TabMeta` (Task 1).
- Produces:
  - `extractTabsFromSource(tsSource: string): TabMeta[]` — eval một module TS data
    thuần export `const TABS = [...]`, trả `[{id,label}]`.
  - `applyTabsToManifest(manifestRaw: string, tabs: TabMeta[]): string`
  - `manifestTabsMatch(manifestRaw: string, tabs: TabMeta[]): boolean`
  - `minderTabsSync(options?: { tabsSource?: string; manifestPath?: string }): Plugin`
    — default `tabsSource='src/dashboard.tabs.ts'`, `manifestPath='../manifest.json'`.

- [ ] **Step 1: Viết test thất bại `minder_ui_sdk/tests/manifestSync.test.ts`**

```ts
import {
  extractTabsFromSource,
  applyTabsToManifest,
  manifestTabsMatch,
} from '../src/manifestSync';

const SRC = `
export const TABS = [
  { id: 'jobs', label: 'Jobs', icon: 'briefcase' },
  { id: 'media', label: 'Media' },
] as const;
`;

it('extracts {id,label} from a plain TS tabs module', () => {
  expect(extractTabsFromSource(SRC)).toEqual([
    { id: 'jobs', label: 'Jobs' },
    { id: 'media', label: 'Media' },
  ]);
});

it('throws when the module does not export a TABS array', () => {
  expect(() => extractTabsFromSource('export const X = 1;')).toThrow();
});

it('merges dashboard.tabs while preserving every other manifest field', () => {
  const manifest = JSON.stringify(
    { display_name: 'Foo', dashboard: { title: 'D', badge_color: 'info' }, remote: { name: 'foo' } },
    null,
    2,
  );
  const out = applyTabsToManifest(manifest, [{ id: 'jobs', label: 'Jobs' }]);
  const parsed = JSON.parse(out);
  expect(parsed.dashboard.tabs).toEqual([{ id: 'jobs', label: 'Jobs' }]);
  expect(parsed.dashboard.title).toBe('D');
  expect(parsed.dashboard.badge_color).toBe('info');
  expect(parsed.remote.name).toBe('foo');
  expect(parsed.display_name).toBe('Foo');
  expect(out.endsWith('\n')).toBe(true);
});

it('creates dashboard when absent', () => {
  const out = applyTabsToManifest('{"display_name":"F"}', [{ id: 'a', label: 'A' }]);
  expect(JSON.parse(out).dashboard.tabs).toEqual([{ id: 'a', label: 'A' }]);
});

it('manifestTabsMatch reports equality by id+label', () => {
  const raw = JSON.stringify({ dashboard: { tabs: [{ id: 'a', label: 'A' }] } });
  expect(manifestTabsMatch(raw, [{ id: 'a', label: 'A' }])).toBe(true);
  expect(manifestTabsMatch(raw, [{ id: 'a', label: 'B' }])).toBe(false);
  expect(manifestTabsMatch('not json', [{ id: 'a', label: 'A' }])).toBe(false);
});
```

- [ ] **Step 2: Chạy test — kỳ vọng FAIL**

Run: `cd minder_ui_sdk && npm test -- manifestSync`
Expected: FAIL — `Cannot find module '../src/manifestSync'`.

- [ ] **Step 3: Viết `minder_ui_sdk/src/manifestSync.ts`**

```ts
import { transformSync } from 'esbuild';
import type { TabMeta } from './types';

/** Strip → {id,label} and drop everything else (icon/component never ship). */
function toWire(tabs: TabMeta[]): Array<{ id: string; label: string }> {
  return tabs.map((t) => ({ id: String(t.id), label: String(t.label) }));
}

/**
 * Evaluate a plain-data tabs module (`export const TABS = [...]`, no React
 * imports) and return the declared tabs. Uses esbuild to strip TS syntax, then
 * runs the emitted CJS in a bare function scope — safe because the module is
 * data only.
 */
export function extractTabsFromSource(tsSource: string): TabMeta[] {
  const { code } = transformSync(tsSource, { loader: 'ts', format: 'cjs' });
  const mod = { exports: {} as Record<string, unknown> };
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  new Function('module', 'exports', code)(mod, mod.exports);
  const tabs = (mod.exports.TABS ?? mod.exports.default) as unknown;
  if (!Array.isArray(tabs)) {
    throw new Error('tabs source must `export const TABS: TabMeta[]`');
  }
  return tabs as TabMeta[];
}

/** Merge tabs into `dashboard.tabs`, preserving all other manifest fields. */
export function applyTabsToManifest(manifestRaw: string, tabs: TabMeta[]): string {
  const manifest = JSON.parse(manifestRaw) as Record<string, unknown>;
  const dashboard = (manifest.dashboard ?? {}) as Record<string, unknown>;
  dashboard.tabs = toWire(tabs);
  manifest.dashboard = dashboard;
  return JSON.stringify(manifest, null, 2) + '\n';
}

/** True when the manifest's dashboard.tabs already equals `tabs` (id+label). */
export function manifestTabsMatch(manifestRaw: string, tabs: TabMeta[]): boolean {
  try {
    const cur = ((JSON.parse(manifestRaw) as any)?.dashboard?.tabs ?? []) as TabMeta[];
    return JSON.stringify(toWire(cur)) === JSON.stringify(toWire(tabs));
  } catch {
    return false;
  }
}
```

- [ ] **Step 4: Chạy test — kỳ vọng PASS**

Run: `cd minder_ui_sdk && npm test -- manifestSync`
Expected: PASS.

- [ ] **Step 5: Viết `minder_ui_sdk/src/vitePlugin.ts`** (không có unit test riêng — logic thuần đã test ở Task 2; plugin chỉ là lớp fs/vite mỏng)

```ts
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';
import { extractTabsFromSource, applyTabsToManifest, manifestTabsMatch } from './manifestSync';

export interface MinderTabsSyncOptions {
  /** TS module exporting `const TABS`. Relative to the vite root. */
  tabsSource?: string;
  /** Module manifest.json to update. Relative to the vite root. */
  manifestPath?: string;
}

/**
 * Vite plugin: keep `manifest.json`'s `dashboard.tabs` in sync with the module's
 * `src/dashboard.tabs.ts`, so the Minder host top-bar shows the right tabs. Fails
 * soft — a missing/broken manifest logs a warning, never breaks the build.
 */
export function minderTabsSync(options: MinderTabsSyncOptions = {}): Plugin {
  const tabsSource = options.tabsSource ?? 'src/dashboard.tabs.ts';
  const manifestPath = options.manifestPath ?? '../manifest.json';
  let root = process.cwd();

  const sync = (warn: (m: string) => void): void => {
    try {
      const tabs = extractTabsFromSource(readFileSync(resolve(root, tabsSource), 'utf8'));
      const mf = resolve(root, manifestPath);
      const raw = readFileSync(mf, 'utf8');
      if (manifestTabsMatch(raw, tabs)) return;
      writeFileSync(mf, applyTabsToManifest(raw, tabs));
      warn(`minder-tabs-sync: wrote ${tabs.length} tab(s) → ${manifestPath}`);
    } catch (e) {
      warn(`minder-tabs-sync: skipped — ${(e as Error).message}`);
    }
  };

  return {
    name: 'minder-tabs-sync',
    configResolved(config) {
      root = config.root;
    },
    buildStart() {
      sync((m) => this.warn(m));
    },
    configureServer(server) {
      const warn = (m: string) => server.config.logger.warn(m);
      sync(warn);
      const abs = resolve(root, tabsSource);
      server.watcher.add(abs);
      server.watcher.on('change', (f) => {
        if (resolve(f) === abs) sync(warn);
      });
    },
  };
}
```

- [ ] **Step 6: Commit**

```bash
git add minder_ui_sdk/src/manifestSync.ts minder_ui_sdk/src/vitePlugin.ts \
  minder_ui_sdk/tests/manifestSync.test.ts
git commit -m "feat(ui-sdk): minderTabsSync vite plugin writes manifest.dashboard.tabs"
```

---

### Task 3: Host — truyền `activeTab` xuống module federation

**Files:**
- Modify: `web-ui/src/components/ModuleDashboard/RemoteDashboard.tsx`
- Modify: `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx:75-97`
- Test: `web-ui/src/components/ModuleDashboard/RemoteDashboard.test.tsx`

**Interfaces:**
- Consumes: store `activeModuleTab` (đã có), `RemoteSummary` (đã có).
- Produces: `RemoteDashboard` nhận thêm prop `activeTab?: string | null` và render
  `<Comp apiBase activeTab />`.

- [ ] **Step 1: Viết test thất bại `web-ui/src/components/ModuleDashboard/RemoteDashboard.test.tsx`**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RemoteDashboard } from './RemoteDashboard';

vi.mock('../../lib/federation', () => ({
  registerRemote: vi.fn(),
  loadRemoteComponent: vi.fn(() =>
    Promise.resolve((props: { apiBase: string; activeTab?: string | null }) => (
      <div data-testid="remote">
        {props.apiBase}|{props.activeTab ?? 'none'}
      </div>
    )),
  ),
}));

const summary = {
  name: 'm',
  remote: true,
  remote_name: 'm',
  remote_entry: 'http://x/dashboard/remoteEntry.js',
  remote_dashboard: './Dashboard',
  api_base: 'http://x',
};

describe('RemoteDashboard', () => {
  it('passes apiBase and activeTab to the federated component', async () => {
    render(<RemoteDashboard summary={summary} activeTab="media" />);
    await waitFor(() => expect(screen.getByTestId('remote')).toBeTruthy());
    expect(screen.getByTestId('remote').textContent).toBe('http://x|media');
  });
});
```

- [ ] **Step 2: Chạy test — kỳ vọng FAIL**

Run: `cd web-ui && npm test -- RemoteDashboard`
Expected: FAIL — component render `http://x|none` (activeTab chưa được truyền).

- [ ] **Step 3: Sửa `RemoteDashboard.tsx`**

Đổi signature + JSX cuối. Thay:
```tsx
export function RemoteDashboard({ summary }: { summary: RemoteSummary }) {
```
thành:
```tsx
export function RemoteDashboard({
  summary,
  activeTab,
}: {
  summary: RemoteSummary;
  activeTab?: string | null;
}) {
```
Và thay dòng render cuối:
```tsx
  return <Comp apiBase={summary.api_base ?? ''} />;
```
thành:
```tsx
  return <Comp apiBase={summary.api_base ?? ''} activeTab={activeTab ?? null} />;
```

- [ ] **Step 4: Sửa `ModuleDashboardView.tsx`** (nhánh remote, quanh dòng 93)

Thay:
```tsx
          <RemoteDashboard summary={summary as any} />
```
thành:
```tsx
          <RemoteDashboard summary={summary as any} activeTab={activeTabId} />
```
(`activeTabId` đã khai báo sẵn tại `const activeTabId = useModulesStore((s) => s.activeModuleTab);`.)

- [ ] **Step 5: Chạy test — kỳ vọng PASS**

Run: `cd web-ui && npm test -- RemoteDashboard`
Expected: PASS — textContent `http://x|media`.

- [ ] **Step 6: Chạy toàn bộ test host để không hồi quy**

Run: `cd web-ui && npm test`
Expected: PASS (gồm `modules.tabs.test.ts` sẵn có).

- [ ] **Step 7: Commit**

```bash
git add web-ui/src/components/ModuleDashboard/RemoteDashboard.tsx \
  web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx \
  web-ui/src/components/ModuleDashboard/RemoteDashboard.test.tsx
git commit -m "feat(web-ui): pass activeTab to federated module dashboards"
```

---

### Task 4: Refactor `module_template` dùng SDK

**Files:**
- Create: `modules/module_template/frontend/src/dashboard.tabs.ts`
- Create: `modules/module_template/frontend/src/ui/StatHeader.tsx`
- Create: `modules/module_template/frontend/src/dashboard.tsx`
- Modify: `modules/module_template/frontend/vite.config.ts`
- Modify: `modules/module_template/frontend/tsconfig.json`
- Delete: `modules/module_template/frontend/src/DashboardApp.tsx`
- (Auto) Modify: `modules/module_template/manifest.json` (plugin ghi `dashboard.tabs`)

**Interfaces:**
- Consumes: `defineDashboard` (Task 1), `minderTabsSync` (Task 2), panels
  `Jobs/Media/Data/MetricsPanel` (đã có, nhận `apiBase`).
- Produces: federated `./Dashboard` = `./src/dashboard.tsx`.

- [ ] **Step 1: Tạo `src/dashboard.tabs.ts`** (data thuần — nguồn tabs duy nhất)

```ts
import type { TabMeta } from 'minder-ui-sdk';

export const TABS: TabMeta[] = [
  { id: 'jobs', label: 'Jobs', icon: 'briefcase' },
  { id: 'media', label: 'Media', icon: 'image' },
  { id: 'data', label: 'Data', icon: 'database' },
  { id: 'metrics', label: 'Metrics', icon: 'bar-chart' },
];
```

- [ ] **Step 2: Tạo `src/ui/StatHeader.tsx`** (tách header + stat cards + health từ `DashboardApp.tsx`)

```tsx
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Briefcase, Image, Database, Activity } from "lucide-react";
import StatCard from "./StatCard";

interface Props {
  apiBase: string;
}

/** Persistent module chrome (brand header + stat cards + health) shown above
 *  whichever tab panel the host has selected. */
export default function StatHeader({ apiBase }: Props) {
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [overview, setOverview] = useState<{ mt_jobs: number; mt_media: number; minder_artifacts_count: number } | null>(null);

  useEffect(() => {
    const check = () => {
      fetch(`${apiBase}/connector/health`)
        .then((r) => r.json())
        .then((d) => setHealthy(!!d.ok))
        .catch(() => setHealthy(false));
    };
    check();
    const t = setInterval(check, 5000);
    return () => clearInterval(t);
  }, [apiBase]);

  useEffect(() => {
    fetch(`${apiBase}/connector/overview`)
      .then((r) => r.json())
      .then(setOverview)
      .catch(() => {});
  }, [apiBase]);

  return (
    <div>
      {/* Header */}
      <div style={{ borderBottom: "1px solid #22304D", padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <span style={{ display: "grid", placeItems: "center", width: 32, height: 32, borderRadius: 9, background: "linear-gradient(135deg, #1E50D8 0%, #2E6BF6 55%, #5AA6FF 100%)", boxShadow: "0 6px 20px rgba(46,107,246,0.40)" }}>
            <Activity size={17} style={{ color: "#fff" }} />
          </span>
          <span style={{ fontWeight: 700, fontSize: 18, letterSpacing: "-0.01em", background: "linear-gradient(90deg, #EAF1FF, #9EC2FF)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent", backgroundClip: "text" }}>Module Template</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <motion.span
            animate={healthy ? { scale: [1, 1.3, 1], opacity: [1, 0.6, 1] } : {}}
            transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
            style={{
              width: 9, height: 9, borderRadius: "50%", display: "inline-block",
              background: healthy === null ? "#f59e0b" : healthy ? "#22c55e" : "#ef4444",
            }}
          />
          <span style={{ color: "#94a3b8" }}>{healthy === null ? "connecting…" : healthy ? "connector online" : "offline"}</span>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ padding: "20px 24px 0" }}>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <StatCard icon={<Briefcase size={20} />} label="Total Jobs" value={overview?.mt_jobs ?? 0} />
          <StatCard icon={<Image size={20} />} label="Media Files" value={overview?.mt_media ?? 0} />
          <StatCard icon={<Database size={20} />} label="Artifacts" value={overview?.minder_artifacts_count ?? 0} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Tạo `src/dashboard.tsx`** (federated entry)

```tsx
import { defineDashboard } from "minder-ui-sdk";
import { ToastProvider } from "./ui/Toast";
import StatHeader from "./ui/StatHeader";
import JobsPanel from "./panels/JobsPanel";
import MediaPanel from "./panels/MediaPanel";
import DataPanel from "./panels/DataPanel";
import MetricsPanel from "./panels/MetricsPanel";
import { TABS } from "./dashboard.tabs";

const Header = ({ apiBase }: { apiBase: string }) => (
  <ToastProvider>
    <StatHeader apiBase={apiBase} />
  </ToastProvider>
);

export default defineDashboard({
  title: "Module Template · SDK showcase",
  header: Header,
  tabs: TABS,
  panels: {
    jobs: JobsPanel,
    media: MediaPanel,
    data: DataPanel,
    metrics: MetricsPanel,
  },
});
```

> Ghi chú: panels dùng `useToast` phải nằm trong `ToastProvider`. Nếu panel nào
> gọi toast, bọc cả shell trong provider ở đây thay vì chỉ header — kiểm tra
> import `useToast` trong 4 panel; nếu có, đổi `Header` slot thành wrap toàn bộ
> bằng cách cho `panels` component tự bọc, hoặc để `ToastProvider` ở `dashboard.tsx`
> cấp cao nhất bằng một `header` wrapper bao trùm. (Xác nhận ở Step 6 khi build.)

- [ ] **Step 4: Sửa `frontend/vite.config.ts`**

Thay toàn bộ file bằng:
```ts
import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';
import { minderTabsSync } from '../../../minder_ui_sdk/src/vitePlugin';

const here = dirname(fileURLToPath(import.meta.url));
const sdk = resolve(here, '../../../minder_ui_sdk/src');

export default defineConfig({
  resolve: {
    alias: { 'minder-ui-sdk': resolve(sdk, 'index.ts') },
  },
  plugins: [
    react(),
    minderTabsSync(),
    federation({
      name: 'module_template',
      filename: 'remoteEntry.js',
      exposes: {
        './Dashboard': './src/dashboard.tsx',
        './ShowcaseBlock': './src/ShowcaseBlock.tsx',
      },
      shared: {
        react: { singleton: true, requiredVersion: '^18.3.1' },
        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },
      },
    }),
  ],
  build: { outDir: 'dist', target: 'esnext' },
  server: { origin: 'http://localhost:9300' },
});
```

- [ ] **Step 5: Sửa `frontend/tsconfig.json`** — thêm `paths` để type-check resolve `minder-ui-sdk`

Trong `compilerOptions`, thêm:
```json
"baseUrl": ".",
"paths": { "minder-ui-sdk": ["../../../minder_ui_sdk/src/index.ts"] }
```

- [ ] **Step 6: Build module — kỳ vọng thành công + manifest có tabs**

Run:
```bash
cd modules/module_template/frontend && npm install && npm run build
```
Expected: build PASS; log `minder-tabs-sync: wrote 4 tab(s) → ../manifest.json`.
Nếu build lỗi do `useToast` ngoài provider, sửa như ghi chú Step 3 rồi build lại.

- [ ] **Step 7: Kiểm tra manifest**

Run: `node -e "const m=require('./modules/module_template/manifest.json');console.log(JSON.stringify(m.dashboard.tabs))"`
Expected: `[{"id":"jobs","label":"Jobs"},{"id":"media","label":"Media"},{"id":"data","label":"Data"},{"id":"metrics","label":"Metrics"}]`

- [ ] **Step 8: Xóa `DashboardApp.tsx`**

Run: `git rm modules/module_template/frontend/src/DashboardApp.tsx`
(Đảm bảo không còn import nào trỏ tới nó: `grep -rn "DashboardApp" modules/module_template/frontend/src` → rỗng.)

- [ ] **Step 9: Commit**

```bash
git add modules/module_template/frontend/src/dashboard.tabs.ts \
  modules/module_template/frontend/src/ui/StatHeader.tsx \
  modules/module_template/frontend/src/dashboard.tsx \
  modules/module_template/frontend/vite.config.ts \
  modules/module_template/frontend/tsconfig.json \
  modules/module_template/manifest.json
git commit -m "feat(module-template): declare tabs via minder-ui-sdk, host owns tab row"
```

---

### Task 5: Scaffolder `service` template dùng SDK

**Files:**
- Modify: `minder/core/modules/service_template.py`
- Test: `tests/test_service_template.py`

**Interfaces:**
- Consumes: pattern từ Task 1/2/4.
- Produces: `service_template.files(name, summary, port)` sinh module mới đã wire
  SDK (`dashboard.tabs.ts`, `dashboard.tsx`, alias + `minderTabsSync` trong vite
  config, tsconfig `paths`, Dockerfile `COPY minder_ui_sdk`, manifest có
  `dashboard.tabs`).

- [ ] **Step 1: Viết test thất bại `tests/test_service_template.py`**

```python
"""Scaffolded service modules must wire the minder-ui-sdk tab contract."""
import json

from minder.core.modules import service_template


def test_files_include_sdk_dashboard_sources():
    files = service_template.files("acme", "demo", port=9400)
    assert "frontend/src/dashboard.tabs.ts" in files
    assert "frontend/src/dashboard.tsx" in files
    assert "frontend/src/DashboardApp.tsx" not in files


def test_vite_config_wires_plugin_and_alias():
    cfg = service_template.frontend_vite_config("acme", 9400)
    assert "minderTabsSync" in cfg
    assert "minder-ui-sdk" in cfg
    assert "./src/dashboard.tsx" in cfg  # exposes the new entry


def test_dashboard_tsx_uses_define_dashboard():
    tsx = service_template.frontend_dashboard_tsx("acme")
    assert "defineDashboard" in tsx
    assert "from 'minder-ui-sdk'" in tsx


def test_tabs_source_exports_plain_data():
    src = service_template.frontend_dashboard_tabs("acme")
    assert "export const TABS" in src


def test_dockerfile_copies_sdk_for_frontend_build():
    df = service_template.backend_dockerfile("acme", 9400)
    assert "COPY minder_ui_sdk /minder_ui_sdk" in df


def test_manifest_declares_dashboard_tabs():
    mf = json.loads(service_template.manifest_json("acme", 9400))
    assert "tabs" in mf["dashboard"]
    assert isinstance(mf["dashboard"]["tabs"], list)
```

- [ ] **Step 2: Chạy test — kỳ vọng FAIL**

Run: `uv run pytest tests/test_service_template.py -v`
Expected: FAIL (các hàm/nội dung chưa tồn tại).

- [ ] **Step 3: `manifest_json` — thêm `"tabs"` vào `dashboard`**

Trong `service_template.py` hàm `manifest_json`, đổi block `"dashboard"`:
```python
        "dashboard": {
            "title": f"{title} · dashboard",
            "default_height": 720,
            "badge_color": "info",
            "tabs": [{"id": "home", "label": "Home"}],
        },
```

- [ ] **Step 4: `frontend_package_json` — thêm devDeps cho panel deps mẫu**

Giữ nguyên; SDK consume qua alias nên KHÔNG thêm `minder-ui-sdk` vào deps.
(Không đổi file này — bước xác nhận: package.json không cần entry SDK.)

- [ ] **Step 5: `frontend_vite_config` — alias + plugin + expose dashboard.tsx**

Thay thân hàm `frontend_vite_config` thành:
```python
def frontend_vite_config(name: str, port: int) -> str:
    return (
        "import { defineConfig } from 'vite';\n"
        "import { fileURLToPath } from 'node:url';\n"
        "import { dirname, resolve } from 'node:path';\n"
        "import react from '@vitejs/plugin-react';\n"
        "import { federation } from '@module-federation/vite';\n"
        "import { minderTabsSync } from '../../../minder_ui_sdk/src/vitePlugin';\n\n"
        "const here = dirname(fileURLToPath(import.meta.url));\n"
        "const sdk = resolve(here, '../../../minder_ui_sdk/src');\n\n"
        "export default defineConfig({\n"
        "  resolve: { alias: { 'minder-ui-sdk': resolve(sdk, 'index.ts') } },\n"
        "  plugins: [\n"
        "    react(),\n"
        "    minderTabsSync(),\n"
        "    federation({\n"
        f"      name: '{name}',\n"
        "      filename: 'remoteEntry.js',\n"
        "      exposes: { './Dashboard': './src/dashboard.tsx' },\n"
        "      shared: {\n"
        "        react: { singleton: true, requiredVersion: '^18.3.1' },\n"
        "        'react-dom': { singleton: true, requiredVersion: '^18.3.1' },\n"
        "      },\n"
        "    }),\n"
        "  ],\n"
        "  build: { outDir: 'dist', target: 'esnext' },\n"
        f"  server: {{ origin: 'http://localhost:{port}' }},\n"
        "});\n"
    )
```

- [ ] **Step 6: `frontend_tsconfig` — thêm baseUrl + paths**

Thay `payload` trong `frontend_tsconfig`:
```python
    payload = {
        "compilerOptions": {
            "target": "esnext",
            "module": "esnext",
            "moduleResolution": "bundler",
            "jsx": "react-jsx",
            "strict": True,
            "skipLibCheck": True,
            "esModuleInterop": True,
            "baseUrl": ".",
            "paths": {"minder-ui-sdk": ["../../../minder_ui_sdk/src/index.ts"]},
        },
        "include": ["src"],
    }
```

- [ ] **Step 7: Thêm `frontend_dashboard_tabs` + đổi `frontend_dashboard_tsx`**

Thêm hàm mới:
```python
def frontend_dashboard_tabs(name: str) -> str:
    return (
        "import type { TabMeta } from 'minder-ui-sdk';\n\n"
        "export const TABS: TabMeta[] = [\n"
        "  { id: 'home', label: 'Home' },\n"
        "];\n"
    )
```

Đổi `frontend_dashboard_tsx` thành shell dùng SDK (panel = UI hỏi/đáp cũ đưa vào `HomePanel`):
```python
def frontend_dashboard_tsx(name: str) -> str:
    title = _title(name)
    return (
        "import { defineDashboard } from 'minder-ui-sdk';\n"
        "import HomePanel from './panels/HomePanel';\n"
        "import { TABS } from './dashboard.tabs';\n\n"
        "export default defineDashboard({\n"
        f"  title: '{title} · dashboard',\n"
        "  tabs: TABS,\n"
        "  panels: { home: HomePanel },\n"
        "});\n"
    )


def frontend_home_panel(name: str) -> str:
    title = _title(name)
    return (
        "import { useEffect, useState } from 'react';\n\n"
        "interface Props {\n"
        "  /** Connector public base, injected by the Minder host. */\n"
        "  apiBase: string;\n"
        "}\n\n"
        f"/** The {name} module's default tab — health + a query box. */\n"
        "export default function HomePanel({ apiBase }: Props) {\n"
        "  const [online, setOnline] = useState<boolean | null>(null);\n"
        "  const [q, setQ] = useState('');\n"
        "  const [answer, setAnswer] = useState('');\n\n"
        "  useEffect(() => {\n"
        "    fetch(`${apiBase}/connector/health`)\n"
        "      .then((r) => r.json())\n"
        "      .then((h) => setOnline(!!h.ok))\n"
        "      .catch(() => setOnline(false));\n"
        "  }, [apiBase]);\n\n"
        "  async function ask() {\n"
        "    const r = await fetch(`${apiBase}/connector/tools/" + name + "_query`, {\n"
        "      method: 'POST',\n"
        "      headers: { 'content-type': 'application/json' },\n"
        "      body: JSON.stringify({ arguments: { query: q } }),\n"
        "    });\n"
        "    const res = await r.json();\n"
        "    setAnswer(typeof res.output === 'string' ? res.output : JSON.stringify(res.output));\n"
        "  }\n\n"
        "  return (\n"
        "    <div style={{ padding: 16 }}>\n"
        f"      <h2>{title}</h2>\n"
        "      <p>Service: {online === null ? 'checking…' : online ? 'online' : 'offline'}</p>\n"
        "      <input value={q} onChange={(e) => setQ(e.target.value)}\n"
        "             placeholder=\"Ask a question…\" style={{ width: '70%' }} />\n"
        "      <button onClick={ask} disabled={!q.trim()}>Ask</button>\n"
        "      {answer && <pre style={{ whiteSpace: 'pre-wrap' }}>{answer}</pre>}\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )
```

- [ ] **Step 8: `frontend_index_html` — trỏ script sang dashboard.tsx**

Trong `frontend_index_html`, đổi:
```python
        "  <script type=\"module\" src=\"/src/DashboardApp.tsx\"></script>\n"
```
thành:
```python
        "  <script type=\"module\" src=\"/src/dashboard.tsx\"></script>\n"
```

- [ ] **Step 9: `backend_dockerfile` — COPY SDK vào frontend stage**

Trong `backend_dockerfile`, ngay trước dòng `RUN npm run build`, thêm 1 dòng COPY.
Đổi block:
```python
        f"COPY modules/{name}/frontend/ ./\n"
        "RUN npm run build\n\n"
```
thành:
```python
        f"COPY modules/{name}/frontend/ ./\n"
        "# minder-ui-sdk is consumed from source via vite alias (../../../minder_ui_sdk).\n"
        "COPY minder_ui_sdk /minder_ui_sdk\n"
        "RUN npm run build\n\n"
```

- [ ] **Step 10: `files()` — cập nhật danh sách file sinh ra**

Trong `files()`, thay 2 dòng frontend dashboard/DashboardApp:
```python
        "frontend/index.html": frontend_index_html(name),
        "frontend/src/DashboardApp.tsx": frontend_dashboard_tsx(name),
```
thành:
```python
        "frontend/index.html": frontend_index_html(name),
        "frontend/src/dashboard.tsx": frontend_dashboard_tsx(name),
        "frontend/src/dashboard.tabs.ts": frontend_dashboard_tabs(name),
        "frontend/src/panels/HomePanel.tsx": frontend_home_panel(name),
```

- [ ] **Step 11: Chạy test — kỳ vọng PASS**

Run: `uv run pytest tests/test_service_template.py -v`
Expected: PASS (6 tests).

- [ ] **Step 12: Commit**

```bash
git add minder/core/modules/service_template.py tests/test_service_template.py
git commit -m "feat(scaffolder): new service modules declare tabs via minder-ui-sdk"
```

---

### Task 6: Kiểm thử end-to-end thật (theo CLAUDE.md)

**Files:** không sửa code — chỉ chạy & quan sát; ghi kết quả.

- [ ] **Step 1: Bảo đảm test JS xanh toàn bộ**

Run:
```bash
cd minder_ui_sdk && npm install && npm test
cd ../web-ui && npm test
```
Expected: tất cả PASS.

- [ ] **Step 2: Bảo đảm test Python xanh**

Run: `uv run pytest tests/test_service_template.py -v` (và `make test` nếu nhanh)
Expected: PASS.

- [ ] **Step 3: Chạy module + web-ui thật**

Run (2 terminal):
```bash
export OPENAI_API_KEY="$OPENAI_API_KEY"
minder-module dev module_template      # backend :9300 + vite dev
make run                               # web-ui host
```

- [ ] **Step 4: Kiểm chứng thủ công trên trình duyệt**

- Mở module Module Template → top-bar hiện 4 tabs (Jobs/Media/Data/Metrics).
- Click từng tab → panel đổi, StatHeader (stat cards + health) giữ nguyên phía trên.
- Đổi sang module khác rồi quay lại → top-bar đổi đúng bộ tabs.
- Sửa `modules/module_template/frontend/src/dashboard.tabs.ts` (đổi 1 label) →
  vite dev ghi lại manifest → sau refresh, top-bar phản ánh label mới.

- [ ] **Step 5: Ghi kết quả e2e** vào `_local/` (không commit) hoặc mô tả trong PR.

---

## Self-Review

**Spec coverage:**
- SoT = TS UI SDK → Task 1 (`defineDashboard`) + Task 4 (`dashboard.tabs.ts`). ✅
- Codegen ghi manifest → Task 2 (`minderTabsSync`) + Task 4 Step 6-7. ✅
- Host truyền `activeTab` (federation) → Task 3. ✅
- Chrome: bỏ tab bar, giữ header/stat → Task 4 (`StatHeader`, không tab bar). ✅
- Package top-level `minder_ui_sdk/` + vite plugin → Task 1/2. ✅
- Scaffolder inherit → Task 5. ✅
- `icon` passthrough, manifest chỉ {id,label} → `applyTabsToManifest` strip. ✅
- Edge cases (fallback tab, no-tabs null, manifest merge/warn) → Task 1 test 2,
  Task 2 tests, plugin fail-soft. ✅
- Testing (unit TS + host + pytest + e2e) → Task 1/2/3/5/6. ✅

**Type consistency:** `TabMeta{id,label,icon?}`, `DashboardProps{apiBase,activeTab?}`,
`defineDashboard(config)→DashboardComponent`, `minderTabsSync(options?)→Plugin`,
`extractTabsFromSource/applyTabsToManifest/manifestTabsMatch` — tên dùng thống
nhất giữa Task 1/2/3/4/5.

**Ghi chú rủi ro đã xử lý:**
- Không thực thi TSX trong plugin → chỉ eval `dashboard.tabs.ts` data thuần.
- Docker frontend stage `COPY minder_ui_sdk /minder_ui_sdk` khớp alias
  `__dirname/../../../minder_ui_sdk` (clamp tại `/`).
- `useToast`/provider: Task 4 Step 3 ghi chú kiểm tra khi build.
