# Module-Centric Web-UI Relayout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the Atria web-ui into a module-centric three-column layout — a collapsible chat rail, a module-UI center driven by a top-bar breadcrumb + tab row, and a toggleable artifact panel — without changing branding or rewriting existing components.

**Architecture:** Approach A (rearrange & reuse). Existing components (`ChatInterface`, `ModuleDashboardView`, `ArtifactViewer`, `ResizeHandle`) are composed into new columns. New work is isolated to: a module-tabs manifest field (backend dataclass + Pydantic + frontend types + store), and three new top-bar/rail widgets (`ModuleBreadcrumb`, `ModuleTabs`, `BlackboardEntry`) plus a `ChatRail` wrapper. No new routes; the module bridge protocol is untouched.

**Tech Stack:** React 18 + TypeScript + Zustand + Tailwind + motion/react (frontend, `web-ui/`); FastAPI + Pydantic + dataclasses (backend, `atria/`). Frontend tests: Vitest (`vitest run`). Backend tests: pytest (`uv run pytest`).

## Global Constraints

- Structural relayout only — keep Atria branding, design tokens, and existing components. No visual reskin (no new fonts, no bento/hero/marquee patterns).
- Frontend line length and style follow existing files; backend line length 100 (Black + Ruff), type hints on public APIs, Google-style docstrings.
- Modules with **no** `tabs` field must behave exactly as today (single `dashboard.html`, empty tab row) — backward compatibility is mandatory.
- The module `useModuleBridge` protocol and `/api/modules/...` routes are NOT changed.
- No new frontend routes. `/blackboard` route stays as-is.
- Run frontend tests with `pnpm test` (alias for `vitest run`) from `web-ui/`; backend tests with `uv run pytest` from repo root.
- Per CLAUDE.md: real end-to-end verification with `OPENAI_API_KEY` set is required in addition to unit tests (final task).

---

## File Structure

**Backend (module-tabs field):**
- Modify `atria/core/modules/store.py` — add `ModuleTabManifest` dataclass + `tabs` on `ModuleDashboardManifest` + parse in `_parse_dashboard()`.
- Modify `atria/web/routes/modules.py` — add `ModuleTabOut` + `tabs` on `ModuleDashboardManifestOut`.
- Test `tests/test_module_tabs_manifest.py` (new).

**Frontend types + store:**
- Modify `web-ui/src/api/modules.ts` — `ModuleTab` interface + `tabs` on `ModuleDashboardManifest`.
- Modify `web-ui/src/stores/modules.ts` — `ModuleTab` on `ModuleSummary`, parse in `summarize()`, `activeModuleTab` state, `setModuleTab`, tab reset in `openDashboard`/`closeDashboard`.
- Test `web-ui/src/stores/modules.tabs.test.ts` (new).

**Frontend components:**
- Modify `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx` — tab-aware `iframeSrc`.
- Create `web-ui/src/components/Layout/ModuleTabs.tsx`.
- Create `web-ui/src/components/Layout/ModuleBreadcrumb.tsx`.
- Create `web-ui/src/components/Layout/BlackboardEntry.tsx`.
- Create `web-ui/src/components/Layout/ChatRail.tsx`.
- Modify `web-ui/src/components/Layout/TopBar.tsx` — swap `ViewSwitcher` for breadcrumb + tabs + blackboard entry.
- Modify `web-ui/src/pages/ChatPage.tsx` — three-column composition, drop center-swap.
- Modify `web-ui/src/components/Layout/MobileTabBar.tsx` — add a "Module" panel.
- Tests: `web-ui/src/components/Layout/ModuleTabs.test.tsx`, `ModuleBreadcrumb.test.tsx` (new).

---

## Task 1: Backend — module `tabs` manifest field

**Files:**
- Modify: `atria/core/modules/store.py:79-82` (dataclass), `atria/core/modules/store.py:277-286` (parse)
- Modify: `atria/web/routes/modules.py:44-49` (Pydantic out model)
- Test: `tests/test_module_tabs_manifest.py`

**Interfaces:**
- Produces: `ModuleTabManifest(id: str, label: str, entry: Optional[str])` dataclass; `ModuleDashboardManifest.tabs: list[ModuleTabManifest]` (default empty list); Pydantic `ModuleTabOut(id, label, entry)` and `ModuleDashboardManifestOut.tabs: List[ModuleTabOut]`. The JSON served at `GET /api/modules` gains `manifest.dashboard.tabs`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_module_tabs_manifest.py`:

```python
"""Tests for the module dashboard `tabs` manifest field."""
from atria.core.modules.store import _parse_dashboard


def test_parse_dashboard_reads_tabs_with_entry_and_hash_mode():
    raw = {
        "title": "Plan board",
        "tabs": [
            {"id": "plan-board", "label": "Plan board", "entry": "dashboard.html"},
            {"id": "readiness", "label": "Readiness"},  # entry omitted -> hash mode
        ],
    }
    dash = _parse_dashboard(raw)
    assert dash is not None
    assert [t.id for t in dash.tabs] == ["plan-board", "readiness"]
    assert dash.tabs[0].entry == "dashboard.html"
    assert dash.tabs[1].entry is None


def test_parse_dashboard_defaults_tabs_to_empty_list():
    dash = _parse_dashboard({"title": "Legacy"})
    assert dash is not None
    assert dash.tabs == []


def test_parse_dashboard_drops_tabs_missing_id_or_label():
    raw = {"tabs": [{"label": "no id"}, {"id": "no-label"}, {"id": "ok", "label": "OK"}]}
    dash = _parse_dashboard(raw)
    assert [t.id for t in dash.tabs] == ["ok"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_module_tabs_manifest.py -v`
Expected: FAIL — `ModuleDashboardManifest` has no attribute `tabs` (AttributeError / TypeError).

- [ ] **Step 3: Add the dataclass + field**

In `atria/core/modules/store.py`, add a `ModuleTabManifest` dataclass immediately before `ModuleDashboardManifest` (before line 78), and add the `tabs` field. Result:

```python
@dataclass
class ModuleTabManifest:
    id: str
    label: str
    entry: Optional[str] = None


@dataclass
class ModuleDashboardManifest:
    title: Optional[str] = None
    default_height: Optional[int] = None
    badge_color: Optional[str] = None
    tabs: list["ModuleTabManifest"] = field(default_factory=list)
```

Ensure `field` is imported: the file already does `from dataclasses import dataclass` — change it to `from dataclasses import dataclass, field` (only if `field` is not already imported).

- [ ] **Step 4: Parse tabs in `_parse_dashboard`**

Replace the `return ModuleDashboardManifest(...)` in `_parse_dashboard` (lines 282-286) with:

```python
    return ModuleDashboardManifest(
        title=_nonempty_str(raw.get("title")),
        default_height=int(height) if isinstance(height, (int, float)) and height > 0 else None,
        badge_color=badge if isinstance(badge, str) and badge in _BADGE_COLORS else None,
        tabs=_parse_tabs(raw.get("tabs")),
    )


def _parse_tabs(raw: Any) -> list[ModuleTabManifest]:
    if not isinstance(raw, list):
        return []
    out: list[ModuleTabManifest] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tab_id = _nonempty_str(item.get("id"))
        label = _nonempty_str(item.get("label"))
        if not tab_id or not label:
            continue
        out.append(ModuleTabManifest(id=tab_id, label=label, entry=_nonempty_str(item.get("entry"))))
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_module_tabs_manifest.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Expose tabs through the API model**

In `atria/web/routes/modules.py`, add above `ModuleDashboardManifestOut` (before line 44):

```python
class ModuleTabOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    label: str
    entry: Optional[str] = None
```

And add the field to `ModuleDashboardManifestOut`:

```python
class ModuleDashboardManifestOut(BaseModel):
    model_config = {"from_attributes": True}

    title: Optional[str] = None
    default_height: Optional[int] = None
    badge_color: Optional[str] = None
    tabs: List[ModuleTabOut] = []
```

`List` is already imported in this file (used by `ModuleOut.files`).

- [ ] **Step 7: Run backend checks**

Run: `uv run pytest tests/test_module_tabs_manifest.py -v && make lint typecheck`
Expected: tests PASS; lint/typecheck clean for the two files.

- [ ] **Step 8: Commit**

```bash
git add atria/core/modules/store.py atria/web/routes/modules.py tests/test_module_tabs_manifest.py
git commit -m "feat(modules): add dashboard tabs manifest field"
```

---

## Task 2: Frontend types + store — tabs & active tab

**Files:**
- Modify: `web-ui/src/api/modules.ts:1-5` (`ModuleDashboardManifest`)
- Modify: `web-ui/src/stores/modules.ts` (`ModuleSummary`, `summarize`, state, actions)
- Test: `web-ui/src/stores/modules.tabs.test.ts`

**Interfaces:**
- Consumes: backend JSON `manifest.dashboard.tabs` from Task 1.
- Produces: `ModuleTab = { id: string; label: string; entry?: string | null }`; `ModuleSummary.tabs: ModuleTab[]`; store state `activeModuleTab: string | null`; action `setModuleTab(id: string): void`. `openDashboard(name)` sets `activeModuleTab` to that module's `tabs[0]?.id ?? null`; `closeDashboard()` sets it to `null`.

- [ ] **Step 1: Write the failing test**

Create `web-ui/src/stores/modules.tabs.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useModulesStore } from './modules';
import type { ModuleSummary } from './modules';

const withTabs: ModuleSummary = {
  name: 'plan', display_name: 'Plan', tooltip: 'Plan', icon_url: null,
  dashboard_title: 'Plan', dashboard_default_height: null, badge_color: null,
  remote: false, remote_name: null, remote_entry: null, remote_dashboard: null,
  api_base: null,
  tabs: [
    { id: 'board', label: 'Board', entry: 'dashboard.html' },
    { id: 'readiness', label: 'Readiness' },
  ],
};
const noTabs: ModuleSummary = { ...withTabs, name: 'legacy', tabs: [] };

beforeEach(() => {
  useModulesStore.setState({
    modulesWithDashboards: [withTabs, noTabs],
    activeModuleDashboard: null,
    activeModuleTab: null,
  });
});

describe('modules store tabs', () => {
  it('openDashboard resets to the first tab', () => {
    useModulesStore.getState().openDashboard('plan');
    expect(useModulesStore.getState().activeModuleTab).toBe('board');
  });

  it('openDashboard on a no-tabs module leaves activeModuleTab null', () => {
    useModulesStore.getState().openDashboard('legacy');
    expect(useModulesStore.getState().activeModuleTab).toBeNull();
  });

  it('setModuleTab changes the active tab', () => {
    useModulesStore.getState().openDashboard('plan');
    useModulesStore.getState().setModuleTab('readiness');
    expect(useModulesStore.getState().activeModuleTab).toBe('readiness');
  });

  it('closeDashboard clears the active tab', () => {
    useModulesStore.getState().openDashboard('plan');
    useModulesStore.getState().closeDashboard();
    expect(useModulesStore.getState().activeModuleTab).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `web-ui/`): `pnpm test src/stores/modules.tabs.test.ts`
Expected: FAIL — `activeModuleTab`/`setModuleTab` do not exist; `ModuleSummary` has no `tabs`.

- [ ] **Step 3: Add the frontend manifest type**

In `web-ui/src/api/modules.ts`, add a `ModuleTab` interface and the `tabs` field:

```ts
export interface ModuleTab {
  id: string;
  label: string;
  entry?: string | null;
}

export interface ModuleDashboardManifest {
  title?: string | null;
  default_height?: number | null;
  badge_color?: string | null;
  tabs?: ModuleTab[] | null;
}
```

- [ ] **Step 4: Add `tabs` to `ModuleSummary` and parse it**

In `web-ui/src/stores/modules.ts`:

1. Import the type: change the existing modules import to also pull `ModuleTab`:
   `import { ModulesApi, type Module, type ModuleTemplate, type ModuleTab } from '../api/modules';`
2. Re-export it for consumers: add `export type { ModuleTab } from '../api/modules';` near the top.
3. Add to the `ModuleSummary` interface: `tabs: ModuleTab[];`
4. In `summarize()`, inside the `.map((m) => { ... })`, after `const dash = mf?.dashboard ?? null;`, add:
   `const tabs = Array.isArray(dash?.tabs) ? dash!.tabs! : [];`
   and add `tabs,` to the returned object literal.

- [ ] **Step 5: Add state + actions**

In `web-ui/src/stores/modules.ts` `interface State`, add:

```ts
  activeModuleTab: string | null;
  setModuleTab: (id: string) => void;
```

In the store initializer, add `activeModuleTab: null,` alongside `activeModuleDashboard: null,`.

Replace `openDashboard` and `closeDashboard` with:

```ts
  openDashboard: (name) => {
    const mod = get().modulesWithDashboards.find((m) => m.name === name);
    if (!mod) return;
    set({ activeModuleDashboard: name, activeModuleTab: mod.tabs[0]?.id ?? null });
  },

  closeDashboard: () => set({ activeModuleDashboard: null, activeModuleTab: null }),

  setModuleTab: (id) => set({ activeModuleTab: id }),
```

Also, in `refresh()`, when `activeModuleDashboard` is no longer present, ensure the tab clears: in the `set((state) => { ... })` block, add `activeModuleTab: stillThere ? state.activeModuleTab : null,` to the returned object.

- [ ] **Step 6: Run test to verify it passes**

Run: `pnpm test src/stores/modules.tabs.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add web-ui/src/api/modules.ts web-ui/src/stores/modules.ts web-ui/src/stores/modules.tabs.test.ts
git commit -m "feat(web-ui): module tabs in store + active tab state"
```

---

## Task 3: Tab-aware iframe src in `ModuleDashboardView`

**Files:**
- Modify: `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx`
- Test: covered by manual E2E in Task 9 (pure URL derivation; unit-tested via helper below)

**Interfaces:**
- Consumes: `activeModuleTab` from store (Task 2), `summary.tabs` (Task 2).
- Produces: exported pure helper `moduleTabSrc(moduleName: string, tab: ModuleTab | null): string` returning the iframe URL for the active tab. Used inside `ModuleDashboardView`.

- [ ] **Step 1: Write the failing test**

Create `web-ui/src/components/ModuleDashboard/moduleTabSrc.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { moduleTabSrc } from './ModuleDashboardView';

describe('moduleTabSrc', () => {
  it('no tab -> base dashboard.html', () => {
    expect(moduleTabSrc('plan', null)).toBe('/api/modules/plan/dashboard.html');
  });
  it('tab with entry -> that entry file', () => {
    expect(moduleTabSrc('plan', { id: 'r', label: 'R', entry: 'readiness.html' }))
      .toBe('/api/modules/plan/readiness.html');
  });
  it('tab without entry -> hash mode on dashboard.html', () => {
    expect(moduleTabSrc('plan', { id: 'scenarios', label: 'S' }))
      .toBe('/api/modules/plan/dashboard.html#scenarios');
  });
  it('encodes the module name', () => {
    expect(moduleTabSrc('a b', null)).toBe('/api/modules/a%20b/dashboard.html');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/ModuleDashboard/moduleTabSrc.test.ts`
Expected: FAIL — `moduleTabSrc` is not exported.

- [ ] **Step 3: Add and export the helper**

In `web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx`, add near the top (after imports), importing the type:

```ts
import type { ModuleTab } from '../../stores/modules';

/** Resolve the iframe URL for a module tab: entry file, hash mode, or base. */
export function moduleTabSrc(moduleName: string, tab: ModuleTab | null): string {
  const base = `/api/modules/${encodeURIComponent(moduleName)}`;
  if (tab?.entry) return `${base}/${tab.entry.replace(/^\/+/, '')}`;
  if (tab) return `${base}/dashboard.html#${tab.id}`;
  return `${base}/dashboard.html`;
}
```

- [ ] **Step 4: Use the helper for `iframeSrc`**

In `ModuleDashboardView`, read the active tab and derive the src. After the existing `summary` selector, add:

```ts
  const activeTabId = useModulesStore((s) => s.activeModuleTab);
  const activeTab = summary?.tabs.find((t) => t.id === activeTabId) ?? null;
```

Replace the existing line
`const iframeSrc = \`/api/modules/${encodeURIComponent(moduleName)}/dashboard.html\`;`
with:
`const iframeSrc = moduleTabSrc(moduleName, activeTab);`

The iframe already keys off `src`, so changing the active tab re-points it. Leave the `useModuleBridge` call unchanged.

- [ ] **Step 5: Run test to verify it passes**

Run: `pnpm test src/components/ModuleDashboard/moduleTabSrc.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add web-ui/src/components/ModuleDashboard/ModuleDashboardView.tsx web-ui/src/components/ModuleDashboard/moduleTabSrc.test.ts
git commit -m "feat(web-ui): tab-aware module dashboard iframe src"
```

---

## Task 4: `ModuleTabs` top-bar component

**Files:**
- Create: `web-ui/src/components/Layout/ModuleTabs.tsx`
- Test: `web-ui/src/components/Layout/ModuleTabs.test.tsx`

**Interfaces:**
- Consumes: store `activeModuleDashboard`, `modulesWithDashboards`, `activeModuleTab`, `setModuleTab` (Task 2).
- Produces: `<ModuleTabs />` — renders the active module's tabs as buttons; nothing (returns `null`) when no module is selected or the module has no tabs. Active tab has `aria-current="page"`.

- [ ] **Step 1: Write the failing test**

Create `web-ui/src/components/Layout/ModuleTabs.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ModuleTabs } from './ModuleTabs';
import { useModulesStore } from '../../stores/modules';

const mod = {
  name: 'plan', display_name: 'Plan', tooltip: 'Plan', icon_url: null,
  dashboard_title: 'Plan', dashboard_default_height: null, badge_color: null,
  remote: false, remote_name: null, remote_entry: null, remote_dashboard: null,
  api_base: null,
  tabs: [{ id: 'board', label: 'Board' }, { id: 'readiness', label: 'Readiness' }],
};

beforeEach(() => {
  useModulesStore.setState({
    modulesWithDashboards: [mod], activeModuleDashboard: 'plan', activeModuleTab: 'board',
  });
});

describe('ModuleTabs', () => {
  it('renders the active module tabs with active marker', () => {
    render(<ModuleTabs />);
    expect(screen.getByRole('button', { name: 'Board' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: 'Readiness' })).not.toHaveAttribute('aria-current');
  });

  it('clicking a tab calls setModuleTab', () => {
    render(<ModuleTabs />);
    fireEvent.click(screen.getByRole('button', { name: 'Readiness' }));
    expect(useModulesStore.getState().activeModuleTab).toBe('readiness');
  });

  it('renders nothing when no module is selected', () => {
    useModulesStore.setState({ activeModuleDashboard: null, activeModuleTab: null });
    const { container } = render(<ModuleTabs />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

Note: if `@testing-library/react` / `jest-dom` are not yet configured, add them in this step — check `web-ui/package.json` devDependencies for `@testing-library/react`; if absent, run `pnpm add -D @testing-library/react @testing-library/jest-dom` and add `import '@testing-library/jest-dom';` to a Vitest setup file referenced by `vite.config.ts` `test.setupFiles` (create `web-ui/src/test-setup.ts` if needed and wire it in `vite.config.ts`).

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/Layout/ModuleTabs.test.tsx`
Expected: FAIL — module `./ModuleTabs` not found.

- [ ] **Step 3: Implement `ModuleTabs`**

Create `web-ui/src/components/Layout/ModuleTabs.tsx`:

```tsx
import { motion, useReducedMotion } from 'motion/react';
import { cn } from '../../lib/cn';
import { useModulesStore } from '../../stores/modules';

/**
 * ModuleTabs — the active module's declared sub-views, rendered as a top-bar
 * tab row. Renders nothing when no module is selected or the module ships no
 * tabs (single-view modules keep their existing single-dashboard behavior).
 */
export function ModuleTabs() {
  const activeName = useModulesStore((s) => s.activeModuleDashboard);
  const modules = useModulesStore((s) => s.modulesWithDashboards);
  const activeTab = useModulesStore((s) => s.activeModuleTab);
  const setModuleTab = useModulesStore((s) => s.setModuleTab);
  const reduce = useReducedMotion();

  const mod = activeName ? modules.find((m) => m.name === activeName) : null;
  if (!mod || mod.tabs.length === 0) return null;

  return (
    <nav aria-label="Module views" className="inline-flex items-center gap-4">
      {mod.tabs.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => setModuleTab(tab.id)}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'relative inline-flex items-center h-8 pb-0.5 text-[13px] font-[480]',
              'tracking-[-0.1px] select-none cursor-pointer transition-colors duration-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/30',
              'focus-visible:ring-offset-1 focus-visible:ring-offset-canvas rounded-sm',
              active ? 'text-ink' : 'text-ink/55 hover:text-ink',
            )}
          >
            <span>{tab.label}</span>
            {active && (
              <motion.span
                layoutId="moduletabs-active"
                className="absolute inset-x-0 -bottom-0.5 h-0.5 rounded-md bg-ink"
                transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 480, damping: 34 }}
                aria-hidden="true"
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/components/Layout/ModuleTabs.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web-ui/src/components/Layout/ModuleTabs.tsx web-ui/src/components/Layout/ModuleTabs.test.tsx web-ui/vite.config.ts web-ui/src/test-setup.ts web-ui/package.json
git commit -m "feat(web-ui): ModuleTabs top-bar component"
```

(Only add the setup/config files if you created them in Step 1.)

---

## Task 5: `ModuleBreadcrumb` module-picker dropdown

**Files:**
- Create: `web-ui/src/components/Layout/ModuleBreadcrumb.tsx`
- Test: `web-ui/src/components/Layout/ModuleBreadcrumb.test.tsx`

**Interfaces:**
- Consumes: store `modulesWithDashboards`, `activeModuleDashboard`, `openDashboard`, `closeDashboard` (Task 2).
- Produces: `<ModuleBreadcrumb />` — a button showing the active module's `display_name` (or "Select module" when none), opening a dropdown listing every module; selecting one calls `openDashboard(name)`.

- [ ] **Step 1: Write the failing test**

Create `web-ui/src/components/Layout/ModuleBreadcrumb.test.tsx`:

```tsx
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ModuleBreadcrumb } from './ModuleBreadcrumb';
import { useModulesStore } from '../../stores/modules';

const base = {
  tooltip: '', icon_url: null, dashboard_title: '', dashboard_default_height: null,
  badge_color: null, remote: false, remote_name: null, remote_entry: null,
  remote_dashboard: null, api_base: null, tabs: [] as { id: string; label: string }[],
};

beforeEach(() => {
  useModulesStore.setState({
    modulesWithDashboards: [
      { ...base, name: 'plan', display_name: 'Plan' },
      { ...base, name: 'move', display_name: 'Move' },
    ],
    activeModuleDashboard: 'plan', activeModuleTab: null,
  });
});

describe('ModuleBreadcrumb', () => {
  it('shows the active module name', () => {
    render(<ModuleBreadcrumb />);
    expect(screen.getByRole('button', { name: /Plan/ })).toBeInTheDocument();
  });

  it('opens the dropdown and selects another module', () => {
    render(<ModuleBreadcrumb />);
    fireEvent.click(screen.getByRole('button', { name: /Plan/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /Move/ }));
    expect(useModulesStore.getState().activeModuleDashboard).toBe('move');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test src/components/Layout/ModuleBreadcrumb.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `ModuleBreadcrumb`**

Create `web-ui/src/components/Layout/ModuleBreadcrumb.tsx`:

```tsx
import { ChevronDown, Package } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { useModulesStore } from '../../stores/modules';

/**
 * ModuleBreadcrumb — top-bar module picker. Shows the active module and opens
 * a dropdown of all modules with dashboards. Replaces the old sidebar Modules
 * list; selecting a module drives the center + ModuleTabs.
 */
export function ModuleBreadcrumb() {
  const modules = useModulesStore((s) => s.modulesWithDashboards);
  const activeName = useModulesStore((s) => s.activeModuleDashboard);
  const openDashboard = useModulesStore((s) => s.openDashboard);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('mousedown', onDown);
    return () => window.removeEventListener('mousedown', onDown);
  }, [open]);

  if (modules.length === 0) return null;
  const active = modules.find((m) => m.name === activeName) ?? null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 h-8 px-2 rounded-md text-[13px] font-[480] text-ink/80 hover:bg-surface-soft hover:text-ink transition-colors cursor-pointer"
      >
        {active?.icon_url ? (
          <img src={active.icon_url} className="h-4 w-4" alt="" />
        ) : (
          <Package className="h-4 w-4 text-ink/50" strokeWidth={1.5} />
        )}
        <span className="truncate max-w-[160px]">{active?.display_name ?? 'Select module'}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: reduce ? 0 : 0.16, ease: [0.16, 1, 0.3, 1] }}
            style={{ transformOrigin: 'top left' }}
            className="absolute left-0 top-full z-50 mt-2 w-64 max-h-80 overflow-y-auto rounded-md border border-hairline-soft bg-canvas shadow-modal py-1"
          >
            {modules.map((m) => {
              const isActive = m.name === activeName;
              return (
                <button
                  key={m.name}
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    openDashboard(m.name);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                    isActive ? 'bg-surface-soft text-ink' : 'text-ink/75 hover:bg-surface-soft hover:text-ink'
                  }`}
                >
                  {m.icon_url ? (
                    <img src={m.icon_url} className="h-4 w-4 flex-shrink-0" alt="" />
                  ) : (
                    <Package className="h-4 w-4 flex-shrink-0 text-ink/40" strokeWidth={1.5} />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-[480]">{m.display_name}</span>
                    {m.tooltip && m.tooltip !== m.display_name && (
                      <span className="block truncate text-[11px] text-ink/45">{m.tooltip}</span>
                    )}
                  </span>
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test src/components/Layout/ModuleBreadcrumb.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add web-ui/src/components/Layout/ModuleBreadcrumb.tsx web-ui/src/components/Layout/ModuleBreadcrumb.test.tsx
git commit -m "feat(web-ui): ModuleBreadcrumb module-picker dropdown"
```

---

## Task 6: `BlackboardEntry` top-bar control

**Files:**
- Create: `web-ui/src/components/Layout/BlackboardEntry.tsx`

**Interfaces:**
- Consumes: `runningSolverCount` + `useSolverJobsStore` (existing, from `../../stores/solverJobs`), `react-router-dom` `Link`/`useLocation`.
- Produces: `<BlackboardEntry />` — a top-bar link to `/blackboard` with the running-jobs badge previously shown by `ViewSwitcher`.

- [ ] **Step 1: Implement the component (reusing ViewSwitcher's badge logic)**

Create `web-ui/src/components/Layout/BlackboardEntry.tsx`:

```tsx
import { LayoutList } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '../../lib/cn';
import { runningSolverCount, useSolverJobsStore } from '../../stores/solverJobs';

/**
 * BlackboardEntry — app-level top-bar link to the Blackboard monitor. Kept
 * separate from the module breadcrumb so the two navigation axes (modules vs
 * the helper monitor) stay distinct. Carries the running-jobs badge.
 */
export function BlackboardEntry() {
  const running = useSolverJobsStore(runningSolverCount);
  const active = useLocation().pathname.startsWith('/blackboard');
  return (
    <Link
      to="/blackboard"
      aria-label={running > 0 ? `Blackboard, ${running} running` : 'Blackboard'}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[13px] font-[480]',
        'transition-colors cursor-pointer',
        active ? 'bg-surface-soft text-ink' : 'text-ink/60 hover:bg-surface-soft hover:text-ink',
      )}
    >
      <LayoutList className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" />
      <span className="hidden lg:inline">Blackboard</span>
      {running > 0 && (
        <span
          className="ml-0.5 inline-flex items-center px-1.5 h-4 rounded-md bg-amber-400/15 text-amber-500 text-[10px] font-mono font-[600] leading-none"
          aria-hidden="true"
        >
          {running}
        </span>
      )}
    </Link>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `pnpm exec tsc --noEmit`
Expected: no errors referencing `BlackboardEntry`.

- [ ] **Step 3: Commit**

```bash
git add web-ui/src/components/Layout/BlackboardEntry.tsx
git commit -m "feat(web-ui): app-level Blackboard top-bar entry"
```

---

## Task 7: `ChatRail` — chat moved into the left rail

**Files:**
- Create: `web-ui/src/components/Layout/ChatRail.tsx`
- Modify: `web-ui/src/components/Layout/ProjectSidebar.tsx` (extract the session/project controls into a reusable body OR reuse in place — see step)

**Interfaces:**
- Consumes: existing `ProjectSidebar` (session list, project switcher, new-chat, collapse) and existing `ChatInterface` (thread + input). Store flags `sidebarCollapsed`, `toggleSidebar` (existing in `stores/chat.ts`).
- Produces: `<ChatRail />` — a vertical column stacking the session/project navigation above `ChatInterface`. Honors `sidebarCollapsed` (thin strip) via the existing `ProjectSidebar` collapsed behavior.

- [ ] **Step 1: Implement `ChatRail` by composing existing components**

`ProjectSidebar` already renders the project switcher, new-chat CTA, Modules list, and Chats list, and already handles its own collapsed/mobile-drawer states and width. For this relayout:

1. Remove the "Modules" section from `ProjectSidebar` (it now lives in `ModuleBreadcrumb`). In `web-ui/src/components/Layout/ProjectSidebar.tsx`, delete the `{modulesWithDashboards.length > 0 && ( ... )}` block inside `sidebarBody` (the `SectionEyebrow label="Modules"` block) and the equivalent module tiles in the collapsed `aside` branch. Remove now-unused imports/vars (`modulesWithDashboards`, `activeModuleDashboard`, `openModuleDashboard`, `closeModuleDashboard`, `Package`, `ModuleHealthDot`, `useModuleHealth`) — let `tsc` guide removal.

2. Create `web-ui/src/components/Layout/ChatRail.tsx`:

```tsx
import { ProjectSidebar } from './ProjectSidebar';
import { ChatInterface } from '../Chat/ChatInterface';
import { useChatStore } from '../../stores/chat';

/**
 * ChatRail — the left column. Stacks the session/project navigation
 * (ProjectSidebar) above the active conversation (ChatInterface). When the
 * rail is collapsed, ProjectSidebar renders its thin-strip form and the
 * conversation is hidden to give the module center full width.
 */
export function ChatRail() {
  const collapsed = useChatStore((s) => s.sidebarCollapsed);
  return (
    <div className="flex h-full min-h-0">
      <ProjectSidebar />
      {!collapsed && (
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r border-hairline-soft/25">
          <ChatInterface />
        </div>
      )}
    </div>
  );
}
```

Note: `ProjectSidebar` keeps its own resizable session-nav width; `ChatInterface` fills the remaining rail width. The whole `ChatRail` occupies the left portion of the page; the module center takes the rest (Task 8). If the combined default is too wide, reduce `ProjectSidebar`'s default `sidebar.width` localStorage default from 256 to 220 in `ProjectSidebar.tsx` — do this only if the E2E in Task 9 shows the rail crowding the center.

- [ ] **Step 2: Verify it compiles and existing store tests pass**

Run: `pnpm exec tsc --noEmit && pnpm test src/stores`
Expected: no type errors; store tests PASS.

- [ ] **Step 3: Commit**

```bash
git add web-ui/src/components/Layout/ChatRail.tsx web-ui/src/components/Layout/ProjectSidebar.tsx
git commit -m "feat(web-ui): ChatRail composing session nav + chat; drop sidebar Modules list"
```

---

## Task 8: Wire the new chrome — `TopBar` + `ChatPage` three-column layout

**Files:**
- Modify: `web-ui/src/components/Layout/TopBar.tsx`
- Modify: `web-ui/src/pages/ChatPage.tsx`
- Modify: `web-ui/src/components/Layout/MobileTabBar.tsx`

**Interfaces:**
- Consumes: `ModuleBreadcrumb` (Task 5), `ModuleTabs` (Task 4), `BlackboardEntry` (Task 6), `ChatRail` (Task 7), `ModuleDashboardView` (Task 3), existing `ArtifactViewer`.
- Produces: the assembled module-centric page. No new exported symbols.

- [ ] **Step 1: Swap TopBar navigation**

In `web-ui/src/components/Layout/TopBar.tsx`:
1. Replace the import `import { ViewSwitcher } from "./ViewSwitcher";` with:
   ```ts
   import { ModuleBreadcrumb } from "./ModuleBreadcrumb";
   import { ModuleTabs } from "./ModuleTabs";
   import { BlackboardEntry } from "./BlackboardEntry";
   ```
2. In the left cluster, replace `<ViewSwitcher />` with `<ModuleBreadcrumb />`.
3. Immediately after the brand/breadcrumb `div` (after the "Left" cluster closes) and before the `<div className="flex-1" />` spacer, insert the tab row:
   ```tsx
   <div className="hidden md:flex min-w-0 items-center overflow-x-auto">
     <ModuleTabs />
   </div>
   ```
4. In the persistent-controls cluster (the final `<div className="flex items-center gap-1 flex-shrink-0">`), add `<BlackboardEntry />` as the first child (before `<TenantSwitcher />`).
5. The mobile hamburger currently guarded by `isChatSurface` should now toggle the chat rail on every surface: change `onClick={openMobileSidebar}` to keep opening the mobile sidebar, but drop the `isChatSurface &&` guard so the rail is reachable. Keep the desktop collapse via the existing Ctrl/Cmd+B shortcut (already wired to `toggleSidebar`).

- [ ] **Step 2: Rebuild ChatPage as three coexisting columns**

In `web-ui/src/pages/ChatPage.tsx`, replace the desktop return and the `centerContent` derivation. The center now shows the module when one is active, else an empty state; chat lives in the rail:

```tsx
import { ChatRail } from '../components/Layout/ChatRail';
// remove the ProjectSidebar + ChatInterface direct imports if now unused in this file
```

Replace the `centerContent` block with:

```tsx
  const centerContent = activeModuleDashboard ? (
    <ModuleDashboardView moduleName={activeModuleDashboard} />
  ) : (
    <div className="flex flex-1 items-center justify-center p-8 text-center">
      <div className="max-w-sm">
        <p className="text-sm text-text-secondary">
          Pick a module from the breadcrumb above, or keep chatting in the left rail.
        </p>
      </div>
    </div>
  );
```

Replace the desktop return with:

```tsx
  // ── Desktop / tablet: chat rail + module center + artifact panel ──
  return (
    <div className="flex-1 min-h-0 flex overflow-hidden bg-bg-000">
      <ChatRail />
      <main className="flex-1 flex flex-col overflow-hidden bg-bg-000 min-w-0">
        {centerContent}
      </main>
      <ArtifactViewer />
      {dialogs}
    </div>
  );
```

For the phone branch: change the `centerContent` used for the `chat` panel to `<ChatInterface />` directly (chat), and add a new `'module'` panel that renders `activeModuleDashboard ? <ModuleDashboardView .../> : centerContent`. Keep `ProjectSidebar` as the drawer. Import `ChatInterface` for the phone chat panel.

- [ ] **Step 3: Add the Module panel to the mobile tab bar**

In `web-ui/src/components/Layout/MobileTabBar.tsx`, add a `'module'` entry to the `MobilePanel` type and a tab button (use the `Package` lucide icon, label "Module"). Wire it in `ChatPage`'s phone `panel` switch from Step 2.

- [ ] **Step 4: Verify compile + full frontend test run**

Run: `pnpm exec tsc --noEmit && pnpm test`
Expected: no type errors; all tests PASS (including existing ones). Fix any references to the removed `ViewSwitcher` (search: `grep -rn ViewSwitcher web-ui/src` — it should only remain as its own now-unused file; leave the file or delete it if nothing imports it).

- [ ] **Step 5: Delete `ViewSwitcher` if unreferenced**

Run: `grep -rn "ViewSwitcher" web-ui/src`
If the only hit is `ViewSwitcher.tsx` itself, delete it: `git rm web-ui/src/components/Layout/ViewSwitcher.tsx`.

- [ ] **Step 6: Commit**

```bash
git add -A web-ui/src
git commit -m "feat(web-ui): module-centric three-column layout (rail + module center + artifacts)"
```

---

## Task 9: Real end-to-end verification (required)

**Files:** none (verification only). Uses a scratch test module.

**Interfaces:** exercises the full chain end-to-end with real API calls.

- [ ] **Step 1: Build the UI and start the app**

```bash
export OPENAI_API_KEY="<your-key>"
make build-ui
make run
```

- [ ] **Step 2: Create a two-tab test module**

Using the Modules UI (or `atria` module tooling), create a module `taberdemo` with a `manifest.json` whose `dashboard.tabs` is:

```json
"tabs": [
  { "id": "board", "label": "Board", "entry": "dashboard.html" },
  { "id": "readiness", "label": "Readiness" }
]
```

Give `dashboard.html` JS that reads `location.hash` and renders "BOARD" vs "READINESS" so hash mode is visibly distinct.

- [ ] **Step 3: Verify each acceptance criterion**

Confirm, observing the running app:
- Chat works in the left rail (send a message, get a real response).
- The breadcrumb dropdown lists modules and selecting `taberdemo` shows its UI in the center.
- The tab row shows Board / Readiness; clicking Readiness switches the center iframe (hash mode renders "READINESS"); Board loads the entry file.
- Collapsing the rail (Ctrl/Cmd+B) gives the module center full width; expanding restores chat.
- Opening a file/artifact slides in the right panel and the center shrinks.
- The Blackboard top-bar entry navigates to `/blackboard`.
- A legacy module with no `tabs` still opens with an empty tab row and its single dashboard.

- [ ] **Step 4: Run the full unit suites once more**

```bash
uv run pytest tests/test_module_tabs_manifest.py -v
cd web-ui && pnpm test
```

Expected: all PASS.

- [ ] **Step 5: Commit any fixes discovered during E2E**

```bash
git add -A
git commit -m "fix(web-ui): address issues found in module-centric relayout E2E"
```

(Skip if no fixes were needed.)

---

## Self-Review Notes

- **Spec coverage:** three-column shell (Task 8), collapsible chat rail (Task 7), toggleable artifact panel (unchanged `ArtifactViewer`, wired in Task 8), breadcrumb dropdown (Task 5), tab row (Task 4), new manifest field with hash + entry-file resolution + no-tabs fallback (Tasks 1-3), app-level Blackboard entry (Task 6). All spec sections map to tasks.
- **Backend requirement caught:** the spec framed tabs as frontend-only, but the strict Pydantic `ModuleDashboardManifestOut` + dataclass `ModuleDashboardManifest` mean `tabs` must be added server-side to survive serialization — covered in Task 1.
- **Type consistency:** `ModuleTab` defined in `api/modules.ts` (Task 2), re-exported from `stores/modules.ts`, consumed by `moduleTabSrc` (Task 3), `ModuleTabs` (Task 4). `activeModuleTab`/`setModuleTab` names are consistent across Tasks 2-4, 8.
- **Test tooling caveat:** component tests (Tasks 4, 5) need `@testing-library/react`; Task 4 Step 1 gates adding it + a Vitest setup file if missing. Store tests (Task 2) need no DOM.
