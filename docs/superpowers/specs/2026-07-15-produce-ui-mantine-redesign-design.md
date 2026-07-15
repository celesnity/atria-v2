# Produce UI — Mantine Redesign Design

**Status:** approved design, pre-plan
**Problem:** the produce dashboard is a monotonous vertical stack of identical full-width
cards — each a title + a few id-inputs + a mostly-empty body with a tiny "empty"
message. It reads like a debug form, not a product. No data density, KPIs, charts,
layout variety, or visual hierarchy.
**Goal:** a real, diverse persona-tailored dashboard using Mantine (+ charts + Tabler
icons), themed to the existing Celesnity tokens, without changing backend behavior.

## Non-goals

- No change to Track A / Track B REST, services, or the `api`/`useApi` data layer.
- No new backend endpoints. Panels keep calling the same routes.
- No host (`web-ui`) changes. This is contained to the produce frontend remote.

## Library stack (Context7-verified, Mantine v8)

Add to `modules/produce/frontend/package.json` dependencies:
`@mantine/core`, `@mantine/hooks`, `@mantine/charts`, `recharts` (peer of charts),
`@tabler/icons-react`. These bundle into the Module-Federation remote (NOT shared
with the host; only `react`/`react-dom` stay shared singletons).

Setup (per Mantine v8 Vite guide):
- Import `@mantine/core/styles.css` and `@mantine/charts/styles.css` once in
  `dashboard.tsx`.
- Wrap the dashboard subtree in
  `<MantineProvider theme={produceTheme} cssVariablesSelector="[data-produce-dashboard]" getRootElement={() => document.querySelector('[data-produce-dashboard]') ?? undefined}>`
  so Mantine CSS variables scope to the dashboard root and reduce leakage into the
  host (Mantine v8 emits styles under `@layer mantine`, so host rules win on
  conflict).
- `produceTheme = createTheme({ primaryColor: 'cobalt', colors: { cobalt: <10-shade tuple derived from Celesnity accent #2563EB> }, defaultRadius: 'md', fontFamily: 'ui-sans-serif, system-ui, ...' })`.

## Component boundaries

- `frontend/src/theme.mantine.ts` — CREATE. `produceTheme` (createTheme) + the cobalt
  tuple + a `statusColorMantine(status)` helper mapping produce statuses to Mantine
  color names (green/blue/orange/red/gray).
- `frontend/src/ui/*` — REPLACE the four primitives with thin Mantine wrappers keeping
  the SAME props so existing panels compile unchanged:
  - `Section({title, actions, children})` → Mantine `Card` (withBorder, radius, shadow)
    + a header row (accent bar + `Title` order 5 + actions group + `Divider`).
  - `DataTable({columns, rows, empty})` → Mantine `Table` (striped, highlightOnHover,
    withTableBorder, stickyHeader) + a composed empty state.
  - `Field/TextInput/NumberInput` → Mantine `TextInput` / `NumberInput` with `label`.
  - `Button({onClick, disabled, variant, children})` → Mantine `Button`
    (variant `filled`/`light`/`outline`; color mapped from produce variant).
  - Keep `Toast` as-is (or swap to `@mantine/notifications` later — out of scope).
- `frontend/src/dashboard.tsx` — MODIFY. Add MantineProvider + styles import. Keep the
  agent-provider gating and `standalone` persona switch (use Mantine `SegmentedControl`).
- `frontend/src/routes/*` + affected panels — RESTRUCTURE per persona (below). Panel
  data logic (state, api calls) is preserved; only the render layout changes.

## Per-persona layout (the diversity)

- **Operator** (`routes/operator.tsx`): top `SimpleGrid` of KPI stat tiles (queue
  count, running job, station status via `RingProgress`/`ThemeIcon` + `Badge`); then a
  responsive `Grid` — left col: task queue list + e-SOP as a Mantine `Stepper`
  (poka-yoke confirm per step); right col: compact WIP action cards (start/complete
  job, count `NumberInput`, scan lot) + downtime/scrap action cards.
- **Tổ trưởng** (`routes/leader.tsx`): team board as a real `Table` with status
  `Badge`s + assign/claim `Button`s; a `Grid` of andon list + open exceptions with
  triage/escalate actions.
- **Quản ca** (`routes/supervisor.tsx`): OEE hero — large `RingProgress` (OEE %) beside
  three loss figures; `DonutChart` (A/P/Q or the three losses) + `BarChart` (top
  downtime); stat tiles; handover + holds below.
- **Quản lý xưởng** (`routes/manager.tsx`): charts-first — `AreaChart` OEE trend across
  shifts, `BarChart` top downtime reasons, `BarChart`/table scrap-by-station; "why
  late" summary tiles.
- **FDE/Admin** (`routes/admin.tsx`): config in a two-column `Grid` of `Card`s (lines /
  stations / operations / parts / skills / SOP / production-order) each with a compact
  form + a `Table`.

Icons: `@tabler/icons-react` (replaces lucide for a distinct look).

## Data / error handling (unchanged contract)

- Reads via `useApi`; mutations via `api()` in try/catch → toast on error, `reload()`
  on success. Backend 409s (poka-yoke / skill-gate) still surface as error toasts.
- Charts read the same aggregation endpoints (`/oee/.../losses`, `/downtime/alerts`,
  `/report/...`, `/scrap/by-station`, `/wip/wip`). Empty/loading states: Mantine
  `Skeleton` while loading, composed empty state when no rows.

## Testing / verification

- `npm run build` green (Vite + Module Federation), no unresolved imports; check the
  Mantine + charts deps resolve and CSS is emitted.
- Rebuild the produce image and load in the Minder host: confirm the five persona
  tabs render the new layouts, charts draw, forms submit, and Mantine styles do NOT
  visibly break the host chrome (scoped via `cssVariablesSelector`).
- Regression: agent-disabled path still renders (standalone), agent path still mounts
  providers + guidance/decision surfaces.

## Risks

- **CSS leakage into the host** — main risk. Mitigate with `cssVariablesSelector`
  scoped to `[data-produce-dashboard]` + Mantine's `@layer mantine`. If leakage is
  still visible, fall back to rendering the dashboard inside a Shadow DOM root
  (follow-up, not this spec).
- **Bundle size** — Mantine core + charts + icons add weight to the remote. Acceptable
  for an internal MES dashboard; tree-shaking keeps unused components out.
