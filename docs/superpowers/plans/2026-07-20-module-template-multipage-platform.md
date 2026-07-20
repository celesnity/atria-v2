# Module Template Multi-page Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a four-page simulated operations platform whose visible controls can be read and operated by Minder through the existing direct WebSocket UI bridge and Embinder approval gate.

**Architecture:** Replace the single Dashboard-local state with a typed `PlatformStore` reducer and deterministic seed data. Render each platform page as a focused component behind a persistent internal navigation rail. Register every readable context and controllable UI operation with the existing direct descriptor adapter; destructive approval decisions route through the existing Embinder hook/relay while other operations execute through the host WebSocket path.

**Tech Stack:** React 18, TypeScript, Vite Module Federation, Vitest, `@embinder/react`, existing direct UI bridge, Docker Compose.

## Global Constraints

- Do not add MCP, connector Python, backend module APIs, worker processes, Celery, registration, or heartbeats.
- Keep the static Module Federation remote contract and the existing one-cursor Embinder visualizer.
- Keep simulated data deterministic and in-memory; do not add an external database.
- Final approval/reject decisions must use the Embinder direct relay gate, not a cosmetic local state transition.
- All shell commands must be prefixed with `rtk`.

---

### Task 1: Establish typed platform state and deterministic commands

**Files:**
- Create: `modules/module_template/frontend/src/platform/types.ts`
- Create: `modules/module_template/frontend/src/platform/store.ts`
- Create: `modules/module_template/frontend/src/platform/store.test.ts`
- Modify: `modules/module_template/frontend/package.json`

**Interfaces:**
- Produces `PlatformState`, `PlatformAction`, `initialPlatformState`, `platformReducer`, and `summarizePlatform(state)`.
- `PlatformAction` has `select_incident`, `analyze_incident`, `move_incident_triage`, `submit_mitigation`, `approve_escalation`, `reject_escalation`, and `reset_platform` variants.
- `summarizePlatform` returns `{ selectedIncidentId, risk, workflowStatus, agentStatus, auditCount }` for `Agent.Data`.

- [ ] **Step 1: Write the failing reducer tests**

```ts
it('records analysis and lowers risk for the selected incident', () => {
  const state = platformReducer(initialPlatformState, { type: 'analyze_incident' });
  expect(state.incidents[0].risk).toBe(41);
  expect(state.audit.at(-1)).toMatchObject({ action: 'analyze_incident', status: 'succeeded' });
});

it('requires a submitted proposal before escalation approval', () => {
  expect(() => platformReducer(initialPlatformState, { type: 'approve_escalation' })).toThrow('proposal_not_pending');
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run src/platform/store.test.ts`

Expected: failure because the test command and `platform/store` module do not exist.

- [ ] **Step 3: Add Vitest and implement the state boundary**

```json
"scripts": { "build": "vite build", "dev": "vite", "test": "vitest" },
"devDependencies": { "vitest": "^2.1.9" }
```

```ts
export type PlatformAction =
  | { type: 'select_incident'; incidentId: string }
  | { type: 'analyze_incident' }
  | { type: 'move_incident_triage' }
  | { type: 'submit_mitigation' }
  | { type: 'approve_escalation' }
  | { type: 'reject_escalation' }
  | { type: 'reset_platform' };

export function platformReducer(state: PlatformState, action: PlatformAction): PlatformState {
  // Return immutable state, append one timestamp-stable audit item per action,
  // and throw `proposal_not_pending` for invalid final decisions.
}
```

- [ ] **Step 4: Run the focused test and production build**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run src/platform/store.test.ts && rtk npm --prefix modules/module_template/frontend run build`

Expected: reducer tests pass and Vite produces `dist/remoteEntry.js`.

- [ ] **Step 5: Commit the state boundary**

```bash
rtk git add modules/module_template/frontend/package.json modules/module_template/frontend/package-lock.json modules/module_template/frontend/src/platform
rtk git commit -m "feat: add module platform state"
```

### Task 2: Add page navigation and the Mission Control/Analyst surfaces

**Files:**
- Create: `modules/module_template/frontend/src/platform/PlatformShell.tsx`
- Create: `modules/module_template/frontend/src/platform/MissionControlPage.tsx`
- Create: `modules/module_template/frontend/src/platform/IncidentAnalystPage.tsx`
- Create: `modules/module_template/frontend/src/platform/platform.test.tsx`
- Modify: `modules/module_template/frontend/src/dashboard.tsx`

**Interfaces:**
- `PlatformShell` accepts `{ activePage: PlatformPage; onNavigate(page: PlatformPage): void; children: ReactNode }`.
- Pages accept `{ state: PlatformState; dispatch(action: PlatformAction): void }`.
- Mission Control and Incident Analyst expose controls with `data-embinder-tool` names `select_incident`, `analyze_incident`, and `move_incident_triage`.

- [ ] **Step 1: Write failing render tests**

```tsx
it('navigates from Mission Control to the Incident & Data Analyst page', async () => {
  render(<Dashboard />);
  await userEvent.click(screen.getByRole('button', { name: 'Incident & Data Analyst' }));
  expect(screen.getByRole('heading', { name: 'Incident & Data Analyst' })).toBeVisible();
});

it('renders an operable analysis control', () => {
  render(<Dashboard />);
  expect(screen.getByRole('button', { name: /Analyze INC-001/ })).toHaveAttribute('data-embinder-tool', 'analyze_incident');
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run src/platform/platform.test.tsx`

Expected: failure because the page components and nav control do not exist.

- [ ] **Step 3: Implement the presentation shell and pages**

```tsx
const pages: Array<{ id: PlatformPage; label: string }> = [
  { id: 'mission-control', label: 'Mission Control' },
  { id: 'incident-analyst', label: 'Incident & Data Analyst' },
  { id: 'workflow-approvals', label: 'Workflow & Approvals' },
  { id: 'activity-audit', label: 'Activity & Audit' },
];

export function PlatformShell({ activePage, onNavigate, children }: PlatformShellProps) {
  return <div><nav aria-label="Platform pages">{pages.map(/* semantic buttons */)}</nav><section>{children}</section></div>;
}
```

Use the existing `Agent.Button` adapter for direct UI actions. Mission Control shows deterministic KPI cards, active incident, agent status, and timeline. Incident Analyst shows the seeded incident table, selected incident details, a CSS/SVG data trend, and analysis/triage controls. Replace the old single screen in `dashboard.tsx` with `useReducer(platformReducer, initialPlatformState)` and page selection state.

- [ ] **Step 4: Run focused tests and build**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run src/platform/platform.test.tsx && rtk npm --prefix modules/module_template/frontend run build`

Expected: page-navigation/action tests pass and the remote builds.

- [ ] **Step 5: Commit the first two pages**

```bash
rtk git add modules/module_template/frontend/src/dashboard.tsx modules/module_template/frontend/src/platform
rtk git commit -m "feat: add platform mission control and analyst pages"
```

### Task 3: Add workflow approval and activity/audit pages

**Files:**
- Create: `modules/module_template/frontend/src/platform/WorkflowApprovalsPage.tsx`
- Create: `modules/module_template/frontend/src/platform/ActivityAuditPage.tsx`
- Modify: `modules/module_template/frontend/src/dashboard.tsx`
- Modify: `modules/module_template/frontend/src/platform/platform.test.tsx`
- Modify: `modules/module_template/frontend/src/embinder.test.ts`

**Interfaces:**
- `WorkflowApprovalsPage` accepts `{ state, dispatch, approveEscalation, rejectEscalation }` where the final two functions return `Promise<unknown>` from `useEmbinder` handlers.
- `ActivityAuditPage` accepts `{ entries: AuditEntry[] }` and renders `entry.correlationId` when present.
- Final action descriptors are `approve_escalation` and `reject_escalation`; proposal submission is `submit_mitigation`.

- [ ] **Step 1: Write failing workflow/audit tests**

```tsx
it('submits then displays a pending approval proposal', async () => {
  render(<Dashboard />);
  await userEvent.click(screen.getByRole('button', { name: 'Workflow & Approvals' }));
  await userEvent.click(screen.getByRole('button', { name: 'Submit mitigation proposal' }));
  expect(screen.getByText('Pending approval')).toBeVisible();
});

it('exposes final approval through an Embinder-gated action', () => {
  const source = readFileSync(new URL('../dashboard.tsx', import.meta.url), 'utf8');
  expect(source).toContain("name: 'approve_escalation'");
  expect(source).toContain('destructive: true');
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run src/platform/platform.test.tsx src/embinder.test.ts`

Expected: failure because the workflow/audit pages and reject operation do not exist.

- [ ] **Step 3: Implement proposal lifecycle and audit rendering**

```tsx
const approve = useEmbinder({
  name: 'approve_escalation', destructive: true,
  handler: () => { dispatch({ type: 'approve_escalation' }); return { ok: true, status: 'approved' }; },
});
const reject = useEmbinder({
  name: 'reject_escalation', destructive: true,
  handler: () => { dispatch({ type: 'reject_escalation' }); return { ok: true, status: 'rejected' }; },
});
```

The submit action creates a pending proposal. Final decision button `onClick` must invoke the corresponding Embinder handler, and the handler dispatches the reducer action only after it is invoked. Activity & Audit renders newest-first entries with semantic status text and a compact empty/error state.

- [ ] **Step 4: Run workflow/audit tests and build**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run src/platform/platform.test.tsx src/embinder.test.ts && rtk npm --prefix modules/module_template/frontend run build`

Expected: all workflow and Embinder source-contract tests pass; Vite build succeeds.

- [ ] **Step 5: Commit workflow and audit pages**

```bash
rtk git add modules/module_template/frontend/src/dashboard.tsx modules/module_template/frontend/src/platform modules/module_template/frontend/src/embinder.test.ts
rtk git commit -m "feat: add platform workflows and audit"
```

### Task 4: Register complete agent context and verify the deployed showcase

**Files:**
- Modify: `modules/module_template/frontend/src/dashboard.tsx`
- Modify: `modules/module_template/frontend/src/embinder.tsx`
- Modify: `modules/module_template/frontend/src/embinder.test.ts`
- Modify: `modules/module_template/embinder.policy.json`
- Modify: `modules/module_template/tests/test_static_host.py`

**Interfaces:**
- The `platform_runtime` `Agent.Data` descriptor returns `summarizePlatform(state)` plus the active page and direct action names.
- `Agent.Button` preserves `data-embinder-tool`, descriptive `aria-label`, and visible button styling for every action.
- The policy allows `select_incident`, `analyze_incident`, `move_incident_triage`, `submit_mitigation`, `approve_escalation`, `reject_escalation`, and `reset_platform`.

- [ ] **Step 1: Write failing bridge/static-host contract tests**

```ts
it('publishes one platform context and all agent action descriptors', () => {
  const source = readFileSync(new URL('./dashboard.tsx', import.meta.url), 'utf8');
  expect(source).toContain('name="platform_runtime"');
  for (const action of ['select_incident', 'analyze_incident', 'submit_mitigation', 'approve_escalation', 'reject_escalation']) {
    expect(source).toContain(action);
  }
});
```

```py
def test_static_remote_serves_multipage_platform_assets(client):
    response = client.get('/dashboard/remoteEntry.js')
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests and confirm the new assertions fail**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run src/embinder.test.ts && rtk uv run pytest modules/module_template/tests/test_static_host.py -q`

Expected: the descriptor assertion fails until `platform_runtime` and all actions are registered.

- [ ] **Step 3: Implement complete descriptors and policy**

```tsx
<Agent.Data
  name="platform_runtime"
  description="Current simulated operations platform state and agent-operable actions."
  value={{ activePage, ...summarizePlatform(state), actions: PLATFORM_ACTION_NAMES }}
>
  {page}
</Agent.Data>
```

Keep `AgentRegistryProvider` as the only direct WebSocket descriptor dispatcher. Do not add a second cursor or SDK chat component. Update policy action names only; keep `unknownTool` destructive and MCP/chat disabled in Compose.

- [ ] **Step 4: Run full validation and recreate the web service**

Run: `rtk npm --prefix modules/module_template/frontend test -- --run && rtk npm --prefix modules/module_template/frontend run build && rtk uv run pytest modules/module_template/tests/test_static_host.py tests/test_ui_sdk_bridge.py -q && rtk docker compose -f modules/module_template/docker-compose.yml up -d --build module-template-web && rtk curl -fsS -o /dev/null -w 'remote=%{http_code}\n' http://127.0.0.1:9300/dashboard/remoteEntry.js && rtk curl -fsS -o /dev/null -w 'mcp=%{http_code}\n' http://127.0.0.1:7331/mcp`

Expected: all tests pass, `remote=200`, and `mcp=404`.

- [ ] **Step 5: Commit the integrated showcase**

```bash
rtk git add modules/module_template/frontend/src modules/module_template/embinder.policy.json modules/module_template/tests/test_static_host.py
rtk git commit -m "feat: expose multipage embinder platform to minder"
```

## Plan self-review

The four tasks cover all four pages, navigation, deterministic shared state,
direct descriptor registration, approval-gated final decisions, cursor
constraint, error/audit behavior, build/test, Docker verification, and MCP
route verification from the approved design. The plan has no placeholders and
the types/action names remain consistent across tasks.
