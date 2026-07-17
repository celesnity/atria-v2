# Produce UI — Mantine Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monotonous stack of identical form-cards with a diverse, persona-tailored Mantine dashboard (KPI tiles, charts, grids) themed to the existing Celesnity tokens — without changing any backend behavior.

**Architecture:** Add Mantine (core + charts + Tabler icons) to the produce Module-Federation remote. A scoped `MantineProvider` themes it to Celesnity. The four shared UI primitives become thin Mantine wrappers keeping the SAME props, so every existing panel upgrades for free. Each persona route is then restructured: KPI stat tiles + charts on top, existing panels reflowed into a responsive grid instead of a vertical stack.

**Tech Stack:** React 18 + Vite + Module Federation; Mantine v8 (`@mantine/core`, `@mantine/hooks`, `@mantine/charts`), `recharts`, `@tabler/icons-react`; existing `api`/`useApi` data layer unchanged.

## Global Constraints

- **No backend change.** Panels keep calling the same REST routes via `api`/`useApi`. No new endpoints. No host (`web-ui`) edits.
- **Mantine v8.** Setup per the Vite guide: import `@mantine/core/styles.css` + `@mantine/charts/styles.css`; wrap in `<MantineProvider theme={produceTheme} cssVariablesSelector="[data-produce-dashboard]" getRootElement={...}>` to scope CSS vars and reduce host leakage (Mantine emits under `@layer mantine`).
- **Keep primitive props identical** so existing panels compile unchanged: `Section({title, actions, children})`; `DataTable<T>({columns, rows, empty})` + `Column<T> = {key, label, render?}`; `Field({label, children})`, `TextInput({value, onChange, placeholder})`, `NumberInput({value, onChange})`; `Button({onClick, disabled, variant, children})` with `variant: 'primary'|'ghost'|'danger'`.
- **Verification is the build gate + visual check.** This is UI: each task ends with `npm run build` green (from `modules/produce/frontend/`); the final task rebuilds the image and loads it in the Minder host. No unit tests are added.
- **Deps bundle into the remote**, not shared with the host. Only `react`/`react-dom` stay federation singletons.
- **Commits:** Conventional Commits; NO `Co-Authored-By: Claude`.

## File Structure

- `frontend/package.json` — add Mantine deps.
- `frontend/src/theme.mantine.ts` — CREATE. `produceTheme` (createTheme, cobalt palette, radius, font) + `statusColorMantine(status)`.
- `frontend/src/ui/Section.tsx` — REPLACE (Mantine Card).
- `frontend/src/ui/DataTable.tsx` — REPLACE (Mantine Table).
- `frontend/src/ui/Field.tsx` — REPLACE (Mantine Input.Wrapper + TextInput/NumberInput).
- `frontend/src/ui/Button.tsx` — REPLACE (Mantine Button).
- `frontend/src/ui/StatTile.tsx` — CREATE. KPI tile.
- `frontend/src/ui/ChartCard.tsx` — CREATE. Card wrapper around a chart with a title.
- `frontend/src/dashboard.tsx` — MODIFY. MantineProvider + styles import; SegmentedControl standalone switch.
- `frontend/src/routes/{operator,leader,supervisor,manager,admin}.tsx` — RESTRUCTURE (grid + tiles + charts).
- A few panels get targeted layout tweaks noted in their persona task.

---

## Phase 1 — Mantine foundation

### Task 1: Add deps + theme

**Files:**
- Modify: `modules/produce/frontend/package.json`
- Create: `modules/produce/frontend/src/theme.mantine.ts`

- [ ] **Step 1: Add dependencies** — in `frontend/package.json`, add to `dependencies`:

```json
    "@mantine/core": "^8.1.1",
    "@mantine/hooks": "^8.1.1",
    "@mantine/charts": "^8.1.1",
    "recharts": "^2.13.3",
    "@tabler/icons-react": "^3.24.0",
```

Then run: `cd modules/produce/frontend && npm install`
Expected: packages install; `node_modules/@mantine/core` exists.

- [ ] **Step 2: Create `frontend/src/theme.mantine.ts`**

```ts
import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Cobalt scale centered on the Celesnity accent #2563EB (Mantine wants 10 shades).
const cobalt: MantineColorsTuple = [
  '#e008f90', // placeholder-safe light 0 (overwritten below)
  '#cfdcfb',
  '#9db6f4',
  '#688eed',
  '#3f6de8',
  '#2559e6',
  '#1a51e5',
  '#0d42cc',
  '#023ab7',
  '#0031a1',
];
cobalt[0] = '#e7f0ff';

export const produceTheme = createTheme({
  primaryColor: 'cobalt',
  colors: { cobalt },
  defaultRadius: 'md',
  fontFamily:
    'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  headings: { fontFamily: 'inherit', sizes: { h5: { fontSize: '14px', fontWeight: '700' } } },
});

// Map a produce status string to a Mantine color name (used by Badge, etc.).
export function statusColorMantine(status: string): string {
  switch (status) {
    case 'queued': case 'idle': case 'open': case 'draft':
      return 'orange';
    case 'assigned': case 'in_progress': case 'running': case 'triaged': case 'setup':
      return 'cobalt';
    case 'done': case 'resolved': case 'approved': case 'released': case 'acknowledged':
      return 'green';
    case 'blocked': case 'down': case 'held': case 'escalated': case 'aborted': case 'retired':
      return 'red';
    default:
      return 'gray';
  }
}
```

- [ ] **Step 3: Build gate** (will still succeed — nothing imports the theme yet)

Run: `cd modules/produce/frontend && npm run build`
Expected: build SUCCEEDS.

- [ ] **Step 4: Commit**

```bash
git add modules/produce/frontend/package.json modules/produce/frontend/package-lock.json modules/produce/frontend/src/theme.mantine.ts
git commit -m "feat(produce/ui): add Mantine deps + Celesnity-mapped theme"
```

### Task 2: Mantine primitive wrappers (upgrade every panel at once)

**Files:**
- Replace: `frontend/src/ui/Section.tsx`, `ui/DataTable.tsx`, `ui/Field.tsx`, `ui/Button.tsx`

**Interfaces (unchanged — panels keep compiling):**
- `Section({title, actions, children})` default; `DataTable<T>({columns, rows, empty})` default + `Column<T>` named; `Field/TextInput/NumberInput` named; `Button({onClick, disabled, variant, children})` default.

- [ ] **Step 1: Replace `ui/Section.tsx`**

```tsx
import type { ReactNode } from 'react';
import { Card, Group, Divider, Title, Box } from '@mantine/core';

export default function Section({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" mb="md">
      <Group justify="space-between" align="flex-end" wrap="nowrap" mb="sm">
        <Group gap={8} align="center" wrap="nowrap">
          <Box w={3} h={16} style={{ borderRadius: 2, background: 'var(--mantine-color-cobalt-6)' }} />
          <Title order={5}>{title}</Title>
        </Group>
        <Group gap={8} align="flex-end" wrap="wrap">{actions}</Group>
      </Group>
      <Divider mb="md" />
      {children}
    </Card>
  );
}
```

- [ ] **Step 2: Replace `ui/DataTable.tsx`**

```tsx
import type { ReactNode } from 'react';
import { Table, Text, Center, Group } from '@mantine/core';

export interface Column<T> { key: string; label: string; render?: (row: T) => ReactNode; }

export default function DataTable<T extends Record<string, unknown>>({ columns, rows, empty = 'Không có dữ liệu' }: { columns: Column<T>[]; rows: T[]; empty?: string }) {
  if (!rows.length) {
    return (
      <Center py="lg">
        <Group gap={8}><Text c="dimmed" size="sm">{empty}</Text></Group>
      </Center>
    );
  }
  return (
    <Table.ScrollContainer minWidth={480}>
      <Table striped highlightOnHover withTableBorder verticalSpacing="xs" horizontalSpacing="md" style={{ fontVariantNumeric: 'tabular-nums' }}>
        <Table.Thead>
          <Table.Tr>
            {columns.map((c) => (
              <Table.Th key={c.key} style={{ textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.03em' }}>{c.label}</Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row, i) => (
            <Table.Tr key={(row.id as number) ?? i}>
              {columns.map((c) => (
                <Table.Td key={c.key}>{c.render ? c.render(row) : String(row[c.key] ?? '')}</Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}
```

- [ ] **Step 3: Replace `ui/Field.tsx`**

```tsx
import type { ReactNode } from 'react';
import { Input, TextInput as MTextInput, NumberInput as MNumberInput } from '@mantine/core';

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <Input.Wrapper label={label} styles={{ label: { textTransform: 'uppercase', fontSize: 11, letterSpacing: '0.03em', fontWeight: 600 } }}>{children}</Input.Wrapper>;
}

export function TextInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return <MTextInput value={value} placeholder={placeholder} onChange={(e) => onChange(e.currentTarget.value)} size="sm" />;
}

export function NumberInput({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return <MNumberInput value={value} onChange={(v) => onChange(typeof v === 'number' ? v : Number(v) || 0)} size="sm" w={110} hideControls />;
}
```

- [ ] **Step 4: Replace `ui/Button.tsx`**

```tsx
import type { ReactNode } from 'react';
import { Button as MButton } from '@mantine/core';

export default function Button({ onClick, disabled, variant = 'primary', children }: { onClick: () => void; disabled?: boolean; variant?: 'primary' | 'ghost' | 'danger'; children: ReactNode }) {
  const map = variant === 'primary'
    ? { color: 'cobalt', variant: 'filled' as const }
    : variant === 'danger'
      ? { color: 'red', variant: 'filled' as const }
      : { color: 'gray', variant: 'default' as const };
  return <MButton size="sm" radius="md" disabled={disabled} onClick={onClick} {...map}>{children}</MButton>;
}
```

- [ ] **Step 5: Build gate**

Run: `cd modules/produce/frontend && npm run build`
Expected: build SUCCEEDS (panels still compile — same prop shapes). Styles will not fully apply until Task 3 mounts MantineProvider.

- [ ] **Step 6: Commit**

```bash
git add modules/produce/frontend/src/ui/Section.tsx modules/produce/frontend/src/ui/DataTable.tsx modules/produce/frontend/src/ui/Field.tsx modules/produce/frontend/src/ui/Button.tsx
git commit -m "feat(produce/ui): Mantine wrappers for Section/DataTable/Field/Button (same props)"
```

### Task 3: MantineProvider + styles in the dashboard shell

**Files:**
- Modify: `frontend/src/dashboard.tsx`

**Interfaces:**
- Consumes: `produceTheme` (Task 1).
- Produces: the whole dashboard subtree is wrapped in `<MantineProvider>`; the standalone persona switch uses Mantine `SegmentedControl`.

- [ ] **Step 1: Add imports at the top of `dashboard.tsx`**

```tsx
import '@mantine/core/styles.css';
import '@mantine/charts/styles.css';
import { MantineProvider, SegmentedControl } from '@mantine/core';
import { produceTheme } from './theme.mantine';
```

- [ ] **Step 2: Replace the `PersonaSwitch` component body** with a Mantine `SegmentedControl`:

```tsx
function PersonaSwitch({ tab, setTab }: { tab: string; setTab: (t: string) => void }) {
  return (
    <SegmentedControl
      value={tab}
      onChange={setTab}
      data={TABS.map((t) => ({ value: t.id, label: t.label }))}
      radius="xl"
      size="sm"
      mb="lg"
    />
  );
}
```

- [ ] **Step 3: Wrap the returned tree in `MantineProvider`.** In BOTH return branches (non-agent and agent), wrap the existing `<MinderThemeProvider …>` element with:

```tsx
  return (
    <MantineProvider theme={produceTheme} cssVariablesSelector="[data-produce-dashboard]" getRootElement={() => document.querySelector('[data-produce-dashboard]') as HTMLElement ?? undefined}>
      {/* existing <MinderThemeProvider> … </MinderThemeProvider> */}
    </MantineProvider>
  );
```

Concretely, change the non-agent branch to:

```tsx
  if (!agentEnabled) {
    return (
      <MantineProvider theme={produceTheme} cssVariablesSelector="[data-produce-dashboard]" getRootElement={() => (document.querySelector('[data-produce-dashboard]') as HTMLElement) ?? undefined}>
        <MinderThemeProvider theme={theme}>
          <ToastProvider>{body}</ToastProvider>
        </MinderThemeProvider>
      </MantineProvider>
    );
  }
```

and the agent branch similarly (wrap its `<MinderThemeProvider>` with the same `<MantineProvider>`).

- [ ] **Step 4: Build gate**

Run: `cd modules/produce/frontend && npm run build`
Expected: build SUCCEEDS. `data-produce-dashboard` already exists on the Surface div (so `getRootElement` resolves once mounted).

- [ ] **Step 5: Commit**

```bash
git add modules/produce/frontend/src/dashboard.tsx
git commit -m "feat(produce/ui): mount scoped MantineProvider + Mantine SegmentedControl switch"
```

---

## Phase 2 — Shared dashboard building blocks

### Task 4: StatTile + ChartCard

**Files:**
- Create: `frontend/src/ui/StatTile.tsx`, `frontend/src/ui/ChartCard.tsx`

**Interfaces:**
- Produces: `StatTile({label, value, icon?, color?, hint?})`; `ChartCard({title, children, actions?})`.

- [ ] **Step 1: Create `frontend/src/ui/StatTile.tsx`**

```tsx
import type { ReactNode } from 'react';
import { Card, Group, Text, ThemeIcon } from '@mantine/core';

export default function StatTile({ label, value, icon, color = 'cobalt', hint }: { label: string; value: ReactNode; icon?: ReactNode; color?: string; hint?: string }) {
  return (
    <Card withBorder radius="lg" padding="md" shadow="xs">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: '0.04em' }}>{label}</Text>
          <Text fw={700} fz={26} lh={1.1} mt={4} style={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Text>
          {hint ? <Text size="xs" c="dimmed" mt={2}>{hint}</Text> : null}
        </div>
        {icon ? <ThemeIcon variant="light" color={color} size={38} radius="md">{icon}</ThemeIcon> : null}
      </Group>
    </Card>
  );
}
```

- [ ] **Step 2: Create `frontend/src/ui/ChartCard.tsx`**

```tsx
import type { ReactNode } from 'react';
import { Card, Group, Title, Box } from '@mantine/core';

export default function ChartCard({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" h="100%">
      <Group justify="space-between" mb="md" align="flex-end">
        <Group gap={8} align="center" wrap="nowrap">
          <Box w={3} h={16} style={{ borderRadius: 2, background: 'var(--mantine-color-cobalt-6)' }} />
          <Title order={5}>{title}</Title>
        </Group>
        {actions}
      </Group>
      {children}
    </Card>
  );
}
```

- [ ] **Step 3: Build gate + commit**

Run: `cd modules/produce/frontend && npm run build` → SUCCEEDS.
```bash
git add modules/produce/frontend/src/ui/StatTile.tsx modules/produce/frontend/src/ui/ChartCard.tsx
git commit -m "feat(produce/ui): StatTile + ChartCard dashboard building blocks"
```

---

## Phase 3 — Persona layouts

> Each persona route composes existing panels inside a Mantine `Grid`/`SimpleGrid` and prepends KPI tiles / charts. Panels keep their data logic; the ROUTE owns the new layout. Tiles/charts fetch via the existing `useApi` from `../api` and the same endpoints the panels use.

### Task 5: Operator route — KPI tiles + two-column grid

**Files:**
- Replace: `frontend/src/routes/operator.tsx`

**Interfaces:**
- Consumes: `useApi` from `../api`; existing panels `WorkPanel`(mode 'queue'), `SopPanel`, `WipPanel`, `DowntimePanel`(mode 'log'), `ScrapPanel`(mode 'record'); `StatTile` (Task 4).

- [ ] **Step 1: Replace `frontend/src/routes/operator.tsx`**

```tsx
import { SimpleGrid, Grid, Stack } from '@mantine/core';
import { IconListCheck, IconClipboardCheck, IconAlertTriangle } from '@tabler/icons-react';
import { useApi } from '../api';
import StatTile from '../ui/StatTile';
import WorkPanel from '../panels/WorkPanel';
import SopPanel from '../panels/SopPanel';
import WipPanel from '../panels/WipPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ScrapPanel from '../panels/ScrapPanel';

export default function OperatorRoute({ apiBase }: { apiBase: string }) {
  const queue = useApi<Array<Record<string, unknown>>>(apiBase, '/work/queue/op1');
  const openDt = useApi<Array<Record<string, unknown>>>(apiBase, '/downtime/events/open');
  const q = queue.data ?? [];
  const running = q.filter((t) => t.status === 'in_progress').length;

  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <StatTile label="Hàng đợi của tôi" value={q.length} icon={<IconListCheck size={20} />} hint="task chưa xong" />
        <StatTile label="Đang làm" value={running} color="green" icon={<IconClipboardCheck size={20} />} />
        <StatTile label="Downtime mở" value={(openDt.data ?? []).length} color="orange" icon={<IconAlertTriangle size={20} />} />
      </SimpleGrid>

      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <WorkPanel apiBase={apiBase} mode="queue" />
          <SopPanel apiBase={apiBase} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <WipPanel apiBase={apiBase} />
          <DowntimePanel apiBase={apiBase} mode="log" />
          <ScrapPanel apiBase={apiBase} mode="record" />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
```

- [ ] **Step 2: Build gate + commit**

Run: `cd modules/produce/frontend && npm run build` → SUCCEEDS.
```bash
git add modules/produce/frontend/src/routes/operator.tsx
git commit -m "feat(produce/ui): operator dashboard — KPI tiles + 2-col grid"
```

### Task 6: Leader route — board + andon/exceptions grid

**Files:**
- Replace: `frontend/src/routes/leader.tsx`

- [ ] **Step 1: Replace `frontend/src/routes/leader.tsx`**

```tsx
import { SimpleGrid, Grid, Stack } from '@mantine/core';
import { IconUsers, IconBellRinging, IconExclamationCircle } from '@tabler/icons-react';
import { useApi } from '../api';
import StatTile from '../ui/StatTile';
import WorkPanel from '../panels/WorkPanel';
import DowntimePanel from '../panels/DowntimePanel';
import ExceptionPanel from '../panels/ExceptionPanel';

export default function LeaderRoute({ apiBase }: { apiBase: string }) {
  const board = useApi<Array<Record<string, unknown>>>(apiBase, '/work/board/1');
  const andons = useApi<Array<Record<string, unknown>>>(apiBase, '/downtime/andon/line/1');
  const exc = useApi<Array<Record<string, unknown>>>(apiBase, '/exception/line/1/open');

  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <StatTile label="Task của tổ" value={(board.data ?? []).length} icon={<IconUsers size={20} />} />
        <StatTile label="Andon đang mở" value={(andons.data ?? []).length} color="orange" icon={<IconBellRinging size={20} />} />
        <StatTile label="Ngoại lệ mở" value={(exc.data ?? []).length} color="red" icon={<IconExclamationCircle size={20} />} />
      </SimpleGrid>

      <WorkPanel apiBase={apiBase} mode="board" />
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 6 }}><DowntimePanel apiBase={apiBase} mode="andon" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><ExceptionPanel apiBase={apiBase} mode="triage" /></Grid.Col>
      </Grid>
    </Stack>
  );
}
```

- [ ] **Step 2: Build gate + commit**

Run: `cd modules/produce/frontend && npm run build` → SUCCEEDS.
```bash
git add modules/produce/frontend/src/routes/leader.tsx
git commit -m "feat(produce/ui): leader dashboard — KPI tiles + board + andon/exception grid"
```

### Task 7: Supervisor route — OEE hero (RingProgress + DonutChart)

**Files:**
- Replace: `frontend/src/routes/supervisor.tsx`
- Create: `frontend/src/panels/OeeHero.tsx`

**Interfaces:**
- Consumes: `useApi`; `RingProgress`, `DonutChart`, `ChartCard`, `StatTile`; existing `OeePanel`, `HandoverPanel`, `ScrapPanel`(hold), `ExceptionPanel`(escalated), `WorkPanel`(load).

- [ ] **Step 1: Create `frontend/src/panels/OeeHero.tsx`**

```tsx
import { useState } from 'react';
import { Card, Group, RingProgress, Text, Stack, NumberInput, SimpleGrid } from '@mantine/core';
import { DonutChart } from '@mantine/charts';
import { useApi } from '../api';

export default function OeeHero({ apiBase }: { apiBase: string }) {
  const [shiftId, setShiftId] = useState(1);
  const [total, setTotal] = useState(400);
  const oee = useApi<Record<string, number> & { error?: string }>(apiBase, `/oee/shifts/${shiftId}?total_count=${total}`, [shiftId, total]);
  const d = oee.data ?? {};
  const pct = (v?: number) => Math.round((v ?? 0) * 100);
  const donut = [
    { name: 'Availability', value: pct(d.availability), color: 'cobalt.6' },
    { name: 'Performance', value: pct(d.performance), color: 'teal.6' },
    { name: 'Quality', value: pct(d.quality), color: 'grape.6' },
  ];
  return (
    <Card withBorder radius="lg" shadow="sm" padding="lg" mb="md">
      <Group justify="space-between" mb="md" align="flex-end">
        <Text fw={700} fz={16}>OEE ca {shiftId}</Text>
        <Group gap="sm">
          <NumberInput label="Ca" value={shiftId} onChange={(v) => setShiftId(Number(v) || 1)} w={90} size="xs" hideControls />
          <NumberInput label="Sản lượng" value={total} onChange={(v) => setTotal(Number(v) || 0)} w={120} size="xs" hideControls />
        </Group>
      </Group>
      {d.error ? (
        <Text c="orange" size="sm">{d.error}</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xl">
          <Group justify="center">
            <RingProgress
              size={180}
              thickness={16}
              roundCaps
              sections={[{ value: pct(d.oee), color: 'cobalt.6' }]}
              label={<Text ta="center" fw={700} fz={30}>{pct(d.oee)}%</Text>}
            />
          </Group>
          <Stack justify="center" gap="xs">
            <DonutChart data={donut} withTooltip chartLabel="A×P×Q" size={150} thickness={22} />
          </Stack>
        </SimpleGrid>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Replace `frontend/src/routes/supervisor.tsx`**

```tsx
import { Grid, Stack } from '@mantine/core';
import OeeHero from '../panels/OeeHero';
import WorkPanel from '../panels/WorkPanel';
import HandoverPanel from '../panels/HandoverPanel';
import ScrapPanel from '../panels/ScrapPanel';
import ExceptionPanel from '../panels/ExceptionPanel';
import OeePanel from '../panels/OeePanel';

export default function SupervisorRoute({ apiBase }: { apiBase: string }) {
  return (
    <Stack gap="md">
      <OeeHero apiBase={apiBase} />
      <Grid gutter="md">
        <Grid.Col span={{ base: 12, lg: 6 }}><WorkPanel apiBase={apiBase} mode="load" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><HandoverPanel apiBase={apiBase} /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><ScrapPanel apiBase={apiBase} mode="hold" /></Grid.Col>
        <Grid.Col span={{ base: 12, lg: 6 }}><ExceptionPanel apiBase={apiBase} mode="escalated" /></Grid.Col>
      </Grid>
      <OeePanel apiBase={apiBase} />
    </Stack>
  );
}
```

- [ ] **Step 3: Build gate + commit**

Run: `cd modules/produce/frontend && npm run build` → SUCCEEDS.
```bash
git add modules/produce/frontend/src/routes/supervisor.tsx modules/produce/frontend/src/panels/OeeHero.tsx
git commit -m "feat(produce/ui): supervisor dashboard — OEE hero (RingProgress + DonutChart)"
```

### Task 8: Manager route — charts-first

**Files:**
- Replace: `frontend/src/routes/manager.tsx`
- Create: `frontend/src/panels/ManagerCharts.tsx`

- [ ] **Step 1: Create `frontend/src/panels/ManagerCharts.tsx`**

```tsx
import { useState } from 'react';
import { SimpleGrid, NumberInput, Group, Text } from '@mantine/core';
import { BarChart } from '@mantine/charts';
import { useApi } from '../api';
import ChartCard from '../ui/ChartCard';

export default function ManagerCharts({ apiBase }: { apiBase: string }) {
  const [lineId, setLineId] = useState(1);
  const [shiftId, setShiftId] = useState(1);
  const why = useApi<{ top_downtime_reasons: Array<Record<string, unknown>>; scrap_by_station: Array<Record<string, unknown>> }>(
    apiBase, `/report/why-late/${lineId}?shift_id=${shiftId}`, [lineId, shiftId],
  );
  const reasons = (why.data?.top_downtime_reasons ?? []).map((r) => ({ category: String(r.category), count: Number(r.count) }));
  const scrap = (why.data?.scrap_by_station ?? []).map((r) => ({ station: `S${r.station_id}`, scrap: Number(r.scrap) }));

  return (
    <>
      <Group mb="md" gap="sm">
        <NumberInput label="Line" value={lineId} onChange={(v) => setLineId(Number(v) || 1)} w={90} size="xs" hideControls />
        <NumberInput label="Ca" value={shiftId} onChange={(v) => setShiftId(Number(v) || 1)} w={90} size="xs" hideControls />
      </Group>
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <ChartCard title="Top lý do downtime">
          {reasons.length ? (
            <BarChart h={240} data={reasons} dataKey="category" series={[{ name: 'count', color: 'cobalt.6' }]} />
          ) : <Text c="dimmed" size="sm">Không có downtime.</Text>}
        </ChartCard>
        <ChartCard title="Phế phẩm theo station">
          {scrap.length ? (
            <BarChart h={240} data={scrap} dataKey="station" series={[{ name: 'scrap', color: 'red.6' }]} />
          ) : <Text c="dimmed" size="sm">Không có phế phẩm.</Text>}
        </ChartCard>
      </SimpleGrid>
    </>
  );
}
```

- [ ] **Step 2: Replace `frontend/src/routes/manager.tsx`**

```tsx
import { Stack } from '@mantine/core';
import ManagerCharts from '../panels/ManagerCharts';
import ReportPanel from '../panels/ReportPanel';

export default function ManagerRoute({ apiBase }: { apiBase: string }) {
  return (
    <Stack gap="md">
      <ManagerCharts apiBase={apiBase} />
      <ReportPanel apiBase={apiBase} />
    </Stack>
  );
}
```

- [ ] **Step 3: Build gate + commit**

Run: `cd modules/produce/frontend && npm run build` → SUCCEEDS.
```bash
git add modules/produce/frontend/src/routes/manager.tsx modules/produce/frontend/src/panels/ManagerCharts.tsx
git commit -m "feat(produce/ui): manager dashboard — downtime + scrap bar charts"
```

### Task 9: Admin route — two-column config grid

**Files:**
- Replace: `frontend/src/routes/admin.tsx`

- [ ] **Step 1: Replace `frontend/src/routes/admin.tsx`**

```tsx
import { Grid, Stack } from '@mantine/core';
import ConfigPanel from '../panels/ConfigPanel';
import SopPanel from '../panels/SopPanel';
import SetupPanel from '../panels/SetupPanel';
import OeePanel from '../panels/OeePanel';

export default function AdminRoute({ apiBase }: { apiBase: string }) {
  return (
    <Grid gutter="md">
      <Grid.Col span={{ base: 12, lg: 7 }}>
        <ConfigPanel apiBase={apiBase} />
      </Grid.Col>
      <Grid.Col span={{ base: 12, lg: 5 }}>
        <Stack gap="md">
          <SopPanel apiBase={apiBase} />
          <SetupPanel apiBase={apiBase} />
          <OeePanel apiBase={apiBase} />
        </Stack>
      </Grid.Col>
    </Grid>
  );
}
```

- [ ] **Step 2: Build gate + commit**

Run: `cd modules/produce/frontend && npm run build` → SUCCEEDS.
```bash
git add modules/produce/frontend/src/routes/admin.tsx
git commit -m "feat(produce/ui): admin dashboard — two-column config grid"
```

---

## Phase 4 — Ship + verify

### Task 10: Rebuild image, visual verification, docs

**Files:**
- Modify: `modules/produce/README.md` (note the Mantine UI stack)

- [ ] **Step 1: Full build gate**

Run: `cd modules/produce/frontend && npm run build`
Expected: SUCCEEDS; `dist/` emitted (the MF DTS type-declaration warning is a known cosmetic non-blocker).

- [ ] **Step 2: Rebuild the running module image**

Run: `docker compose --env-file .env -f modules/produce/docker-compose.yml up -d --build produce-web`
Then: `curl -s -m 5 -o /dev/null -w "%{http_code}\n" localhost:9310/` → `200`.

- [ ] **Step 3: Visual verification in the Minder host**

Open `http://localhost:8080`, load the produce module, and click each persona tab:
- Operator: 3 KPI tiles + 2-col grid render; forms/tables are Mantine-styled.
- Tổ trưởng: tiles + board table + andon/exception grid.
- Quản ca: OEE RingProgress + DonutChart draw; grid below.
- Quản lý xưởng: two bar charts draw.
- FDE/Admin: two-column config.
Confirm the host chrome (top bar, chat) is NOT visibly broken by Mantine styles (scoped via `cssVariablesSelector`). If host styles leak, note it for the Shadow-DOM follow-up (do not block).

- [ ] **Step 4: Docs** — add one line to `modules/produce/README.md` under the UI section: the dashboard uses Mantine v8 (core + charts) + Tabler icons, themed to Celesnity, scoped via `cssVariablesSelector`.

- [ ] **Step 5: Commit**

```bash
git add modules/produce/README.md
git commit -m "docs(produce): note Mantine UI stack"
```

---

## Self-Review

**Spec coverage:** library stack + setup → Task 1, 3; scoped MantineProvider → Task 3; primitive wrappers (same props) → Task 2; StatTile/ChartCard → Task 4; per-persona layouts (Operator/Leader/Supervisor/Manager/Admin) → Tasks 5-9; charts (RingProgress/DonutChart/BarChart) → Tasks 7-8; Tabler icons → Tasks 5-6; no-backend-change + build-gate verification → Global Constraints + every task; image rebuild + visual verify + CSS-leak risk → Task 10.

**Placeholder scan:** No TBD/TODO. The cobalt tuple index 0 is set explicitly (`cobalt[0] = '#e7f0ff'`) to avoid a bogus first hex; all component code is complete. Every step shows the full file or the exact insertion.

**Type consistency:** primitive prop shapes are unchanged from the current code (verified against the existing panels' usage — `Section({title,actions,children})`, `Column<T>={key,label,render?}`, `Field/TextInput/NumberInput`, `Button variant 'primary'|'ghost'|'danger'`). `StatTile({label,value,icon?,color?,hint?})` and `ChartCard({title,actions?,children})` are used consistently in Tasks 5-8. `useApi(base, path, deps?)` matches the existing hook. Mantine `NumberInput onChange` yields `number|string` — every call coerces with `Number(v)||…`.

**Known caveat (not a blocker):** some panels render their form controls in raw `<div style={{display:'flex'}}>` rows; inside Mantine these still work (the wrappers render Mantine inputs). If any panel's inline flexbox looks cramped, a follow-up can swap it for Mantine `Group`, but that is out of this plan's scope — the persona-route grids + tiles + charts deliver the "diverse layout" the spec requires.
