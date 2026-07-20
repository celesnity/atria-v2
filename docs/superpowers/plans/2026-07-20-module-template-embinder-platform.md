# Module Template Embinder Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task with TDD checkpoints.

**Goal:** Build a deterministic operations platform in Module Template using the real Embinder React SDK, SDK-gated approval, and no MCP.

**Architecture:** The static remote imports `@embinder/react`. A private relay carries only app registration, policy, approval, audit, spotlight, and browser calls. Minder remains the chat/runtime and reaches the module only through `ui_describe` and `ui_act`.

**Tech Stack:** React, TypeScript, Vite Federation, Embinder React/relay, FastAPI WebSocket bridge, Docker Compose, Vitest, pytest.

## Global Constraints

- Keep `minderSDK/` untracked by Minder; commit SDK modifications only in its nested repository.
- `EMBINDER_ENABLE_MCP=false` and `EMBINDER_ENABLE_CHAT=false` are mandatory.
- Do not restore connector APIs, Python services, workers, Celery, registration, heartbeat, or health polling.
- The platform uses deterministic local data and has a reset action.

## File Structure

- `minderSDK/packages/relay/src/server.ts`: no-MCP flags and direct gate route.
- `minderSDK/packages/relay/src/server.no-mcp.test.ts`: relay contract tests.
- `modules/module_template/embinder.policy.json`: risk mapping.
- `modules/module_template/relay/Dockerfile`: relay image.
- `modules/module_template/docker-compose.yml`: static remote and relay runtime.
- `modules/module_template/frontend/src/platform/model.ts`: simulated data and reducer.
- `modules/module_template/frontend/src/platform/Platform.tsx`: SDK component platform.
- `modules/module_template/frontend/src/embinder.tsx`: direct bridge/SDK action adapter.
- `minder/web/ui_sdk_bridge.py`: approval-sized waits.

### Task 1: Implement a no-MCP relay direct-gate mode

**Files:** Modify `minderSDK/packages/relay/src/server.ts`; create `minderSDK/packages/relay/src/server.no-mcp.test.ts`.

**Interfaces:** Add `POST /internal/direct-call`, authenticated by `x-embinder-direct-token`, and `GET /internal/ready`. Add `EMBINDER_ENABLE_MCP`, `EMBINDER_ENABLE_CHAT`, `EMBINDER_DIRECT_TOKEN`, `EMBINDER_POLICY_PATH`, and `EMBINDER_AUDIT_PATH`.

- [ ] **Step 1: Write failing tests.** Assert `POST /mcp` returns 404 when MCP is disabled. Register `approve_escalation` with destructive risk, call `/internal/direct-call`, assert it remains pending until approval, then returns the browser action result. Assert deny does not call the browser handler.
- [ ] **Step 2: Verify RED.** Run `cd minderSDK && npm --workspace @embinder/relay test -- server.no-mcp.test.ts`; expect missing endpoint/feature flag failures.
- [ ] **Step 3: Implement only the new boundary.** Derive feature flags once from environment. Extract current MCP routes to `mountMcpRoutes()` and invoke it only when MCP is enabled. Gate chat mounts on the chat flag. For the direct route, look up the registered capability and pass its actual destructive flag to `runGatedCall`; never accept risk from the HTTP body.
- [ ] **Step 4: Verify GREEN.** Run `cd minderSDK && npm --workspace @embinder/relay test -- server.no-mcp.test.ts && npm --workspace @embinder/relay run typecheck`; expect PASS.
- [ ] **Step 5: Commit nested SDK work.** Run `cd minderSDK && git add packages/relay/src/server.ts packages/relay/src/server.no-mcp.test.ts && git commit -m "feat(relay): add no-mcp direct gate mode"`.

### Task 2: Add the private relay runtime to Module Template

**Files:** Create `modules/module_template/embinder.policy.json` and `modules/module_template/relay/Dockerfile`; modify `modules/module_template/docker-compose.yml` and `modules/module_template/tests/test_static_host.py`.

**Interfaces:** Browser attaches to `ws://localhost:7331/app`; the static module uses Docker address `http://module-template-embinder-relay:7331/internal/direct-call`.

- [ ] **Step 1: Write a failing static-runtime test.** Assert compose contains service `module-template-embinder-relay`, `EMBINDER_ENABLE_MCP=false`, and `EMBINDER_ENABLE_CHAT=false`.
- [ ] **Step 2: Verify RED.** Run `uv run pytest modules/module_template/tests/test_static_host.py -q`; expect failure because service does not exist.
- [ ] **Step 3: Add policy and container.** Configure `platform_context` as read; selection, analysis, triage movement, proposal submission, and reset as write; `approve_escalation` and `reject_escalation` as destructive. Pass policy/audit paths and a direct-call token via Compose. Expose only port 7331 for the browser protocol; do not document or mount MCP.
- [ ] **Step 4: Verify GREEN.** Run `uv run pytest modules/module_template/tests/test_static_host.py -q && docker compose -f modules/module_template/docker-compose.yml up -d --build && curl -s -o /dev/null -w '%{http_code}\\n' http://127.0.0.1:7331/mcp`; expect test PASS and 404.
- [ ] **Step 5: Commit runtime config.** Run `git add modules/module_template/embinder.policy.json modules/module_template/relay/Dockerfile modules/module_template/docker-compose.yml modules/module_template/tests/test_static_host.py && git commit -m "feat: run embinder gate without mcp"`.

### Task 3: Make `ui_act` wait for approval safely

**Files:** Modify `minder/web/ui_sdk_bridge.py` and `tests/test_ui_sdk_bridge.py`.

**Interfaces:** `DirectUiSdkBridge.invoke(..., timeout: float = 120.0)` rejects values below one second and preserves correlation/Future cleanup.

- [ ] **Step 1: Write failing async test.** Start `bridge.invoke("s-1", "module_template", "approve_escalation", {}, timeout=0.2)`, resolve its known correlation id before expiry, and assert `{ "ok": True }` returns. Test rejection for `timeout=0`.
- [ ] **Step 2: Verify RED.** Run `uv run pytest tests/test_ui_sdk_bridge.py -q`; expect the fixed short timeout contract to fail the new assertion.
- [ ] **Step 3: Add `DEFAULT_UI_ACTION_TIMEOUT_SECONDS = 120.0`; use it only for action invocation.** Keep `ui_describe` unchanged and reject timeout values below one second.
- [ ] **Step 4: Verify GREEN and commit.** Run `uv run pytest tests/test_ui_sdk_bridge.py -q`; expect PASS. Commit with `git add minder/web/ui_sdk_bridge.py tests/test_ui_sdk_bridge.py && git commit -m "feat: allow direct ui actions to await approval"`.

### Task 4: Model deterministic platform state and action coordination

**Files:** Create `modules/module_template/frontend/src/platform/model.ts` and `model.test.ts`; modify `modules/module_template/frontend/src/embinder.tsx`.

**Interfaces:** Export `createInitialPlatformState()`, `platformReducer(state, event)`, `buildPlatformContext(state)`, and direct action registration. Events are `incident_selected`, `incident_analyzed`, `incident_moved`, `proposal_submitted`, `approval_approved`, `approval_denied`, and `platform_reset`.

- [ ] **Step 1: Write failing model tests.** Assert initial selected incident is `inc-001`, no proposals exist, and approval is idle. Submit proposal `prop-001`, deny it, and assert it remains pending; reset and assert exact initial state.
- [ ] **Step 2: Verify RED.** Run `npm --prefix modules/module_template/frontend test -- --run src/platform/model.test.ts`; expect missing module errors.
- [ ] **Step 3: Implement reducer and context.** Store stable incidents, event stream, triage lane, proposals, approval status, and activity entries. Use the exact same action callback for direct bridge registration and SDK pointer handler. For destructive direct actions, post to Task 1 internal route; do not mutate before the SDK browser call returns.
- [ ] **Step 4: Verify GREEN and commit.** Run `npm --prefix modules/module_template/frontend test -- --run src/platform/model.test.ts && npm --prefix modules/module_template/frontend run build`; expect PASS. Commit platform model and adapter.

### Task 5: Build the normal platform from official SDK primitives

**Files:** Create `modules/module_template/frontend/src/platform/Platform.tsx` and `Platform.test.tsx`; modify `dashboard.tsx`, `vite.config.ts`, and `package.json`.

**Interfaces:** `Platform` renders Overview, Incidents, Analysis, Triage, Proposals, Approvals, and Activity. Vite aliases `@embinder/react` to the local SDK source.

- [ ] **Step 1: Write failing UI tests.** Render Platform; expect heading `Operations platform` and incident `INC-001`. Complete recommendation form with `Route traffic to the safe model`; expect `Pending approval`.
- [ ] **Step 2: Verify RED.** Run `npm --prefix modules/module_template/frontend test -- --run src/platform/Platform.test.tsx`; expect missing component failure.
- [ ] **Step 3: Implement semantic SDK surface.** Use `EmbinderProvider` with `viz` and `chat={false}`, `AgentScope` for Overview/Analysis/Triage/Approvals, `AgentList` for incidents/proposals, `AgentForm` for mitigation, and Agent input/select/toggle/checkbox/radio/button/link/div components where native behavior matches visible UI. Register scroll targets, routes, draggables, and drop zones. Anchor destructive controls with `grabAnchor` for spotlight/lock. Keep Minder mascot outside the SDK chat component.
- [ ] **Step 4: Verify GREEN and commit.** Run `npm --prefix modules/module_template/frontend test -- --run src/platform/Platform.test.tsx && npm --prefix modules/module_template/frontend run build`; expect PASS. Commit dashboard, platform, alias, and dependencies.

### Task 6: Prove the complete no-MCP flow

**Files:** Modify `tests/test_module_template_ui_only.py` and `README.md`.

- [ ] **Step 1: Write failing contract test.** Assert dashboard contains `EmbinderProvider` and `chat={false}`; compose contains `EMBINDER_ENABLE_MCP=false`; compose has no `connector_url`.
- [ ] **Step 2: Verify RED then GREEN.** Run `uv run pytest tests/test_module_template_ui_only.py -q`; make it pass after Tasks 2 and 5.
- [ ] **Step 3: Run real demo.** Start Core and module compose, verify remote health and `/mcp` 404. In Core ask: `Call ui_describe, analyze inc-001, create a mitigation proposal, request approval, approve it, then call ui_describe again.` Verify ghost cursor, spotlight lock, Deny-without-mutation, Approve transition, and activity/audit update.
- [ ] **Step 4: Run final checks and commit.** Run `uv run pytest tests/test_module_template_ui_only.py tests/test_ui_sdk_bridge.py -q && npm --prefix web-ui run build && npm --prefix modules/module_template/frontend run build`; expect PASS. Commit docs, contracts, and generated static output.
