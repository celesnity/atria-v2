# Module-Centric Web-UI Relayout — Design

**Date:** 2026-07-12
**Status:** Approved (design) — pending spec review
**Scope:** `web-ui/` (Atria web frontend)

## Problem

Today the web-ui is chat-first: chat fills the center, and modules are a
secondary list buried in the left sidebar. As modules become the primary
work surface (each shipping its own dashboard UI), this inverts the natural
hierarchy — the user has to leave chat to open a module, and modules have no
room to present multiple views.

We are relayouting the app to be **module-centric**: the module's UI owns the
center, chat becomes a persistent collaborator rail on the left, and module
navigation is promoted into the top bar.

This is a **structural relayout only** — Atria's existing branding, design
tokens, and components are kept. The reference mockup ("Minder") is a layout
reference, not a pixel or visual-reskin target.

## Decisions (locked)

1. **Fidelity:** Structural relayout only. Keep Atria branding, colors, and
   existing components. Do not apply an elite visual reskin.
2. **Module navigation:** A top-bar **breadcrumb dropdown** picks the active
   module; a **tab row** shows that module's sub-views. Module sub-views are a
   **new manifest/SDK capability**.
3. **Chat placement:** Chat lives in a **collapsible left rail**, coexisting
   with the module center (they no longer swap the center).
4. **Blackboard:** Stays an **app-level top-bar entry**, outside the module
   dropdown. `/blackboard` route unchanged.
5. **Artifacts:** The file explorer + code editor stays a **toggleable right
   panel** that slides in when a file/artifact opens.
6. **Implementation approach:** **Rearrange & reuse** existing components
   (`ChatInterface`, `ModuleDashboardView`, `ArtifactViewer`, `ResizeHandle`,
   etc.). Isolate genuinely new work to the tab mechanism and two top-bar
   widgets. No route refactor.

## Target Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ TopBar:  [≡] ◆ Atria  /  Plan ▾   │  tab tab tab tab   🔍 Blackboard        │
│                                    │                    tenant ☾ ⚙ MS        │
├────────────┬───────────────────────────────────────────┬───────────────────┤
│ Chat rail  │   Active module UI (selected tab)          │  Artifact panel   │
│ collapsible│   = ModuleDashboardView iframe             │  (slides in when  │
│  sessions  │                                            │   a file opens)   │
│  ─────────  │   empty state (module picker) when none   │   toggleable      │
│  thread    │                                            │                   │
│  input     │                                            │                   │
└────────────┴───────────────────────────────────────────┴───────────────────┘
```

- **TopBar** stays mounted once in `AppShell` (as today) so it never flickers
  on navigation.
- **Left rail** = chat, collapsible to a thin strip (reuses existing collapse
  pattern + `ResizeHandle`).
- **Center** = active module's UI, or an empty "pick a module / start chatting"
  state when none is selected.
- **Right** = `ArtifactViewer`, unchanged — hidden until a file/artifact opens,
  then slides in and the center shrinks.
- The old center-swapping logic (`centerContent = dashboard ? … : chat`) is
  **removed**; chat and module occupy different columns.

## Component Design

### Top bar (`TopBar`)

**Left cluster:** `[≡] ◆ Atria / <Module ▾>`
- `[≡]` collapses the chat rail (replaces today's sidebar hamburger role).
- `◆ Atria` brand — unchanged.
- **`ModuleBreadcrumb`** (new): button showing the active module name +
  chevron. Opens the **module-picker dropdown** listing every module from
  `modulesWithDashboards` (icon, display name, tooltip/description). Selecting
  sets `activeModuleDashboard` and resets to the module's first tab. This
  replaces the "Modules" list previously in the left sidebar. The old
  `ViewSwitcher` (Chat/Blackboard segmented control) is retired from the bar.

**Center-left — `ModuleTabs`** (new): renders the active module's declared tabs
with an active-tab underline (reuses the `ViewSwitcher` underline-motion
pattern). Empty when the active module declares no tabs; hidden entirely when
no module is selected.

**Right cluster (preserved + one addition):**
- **Blackboard** app-level entry (new small control — icon/pill link to
  `/blackboard`, carrying the running-jobs badge `ViewSwitcher` used to show).
- Existing chat status pills (cost, context %, connection, ⌘K) — shown when a
  session is live.
- `TenantSwitcher`, theme toggle, settings, account menu — unchanged.

### Chat rail (`ChatRail`, new)

Merges the sidebar's session list and the center's `ChatInterface` into one
vertical stack:

```
┌────────────────────────┐
│ Workspace ▾   + ⚙       │  project switcher + new-chat + settings
├────────────────────────┤
│ SESSION CHATS           │  session list (scrollable, capped height)
├────────────────────────┤
│ [active conversation]   │  ChatInterface thread (fills remaining height)
├────────────────────────┤
│ Ask about this… ▶       │  ChatInterface input, pinned bottom
└────────────────────────┘
```

- **Composition:** stacks (a) project/session controls extracted from
  `ProjectSidebar` and (b) the existing `ChatInterface` (thread + input). Reuse
  `ChatInterface` as-is; it now lives in a ~320–360px resizable column.
- **Collapsible:** reuses the current `sidebarCollapsed` flag + `ResizeHandle`.
  Collapsed → thin strip with new-chat + session icons, giving the module
  center full width.
- **Session/thread split:** session list gets a capped, scrollable max-height so
  the active thread always has room; on short viewports it collapses to a
  compact dropdown.
- **Mobile:** rail becomes the off-canvas drawer it already is; `MobileTabBar`
  gains a "Module" panel alongside chat/files/editor.
- **Note:** `ChatInterface` currently assumes a wide center. Fitting it to the
  narrow rail is mostly CSS (message max-width, input sizing) — no logic
  changes. Flag any genuine responsive tweak during planning; do not rewrite it.

### Module tabs (new manifest/SDK capability)

A module declares its sub-views in its manifest; the host renders them as the
tab row and swaps the iframe accordingly.

**Manifest shape** (extends `ModuleDashboardManifest`):

```jsonc
"dashboard": {
  "title": "Plan board",
  "tabs": [
    { "id": "plan-board",  "label": "Plan board",  "entry": "dashboard.html" },
    { "id": "readiness",   "label": "Readiness",   "entry": "readiness.html" },
    { "id": "scenarios",   "label": "Scenarios" },   // entry omitted → hash mode
    { "id": "commitments", "label": "Commitments" },
    { "id": "history",     "label": "History" }
  ]
}
```

**Tab content resolution** (author picks per tab):
- **Separate entry file** — `entry: "readiness.html"` → iframe loads
  `/api/modules/<name>/readiness.html`.
- **Hash mode (default when `entry` omitted)** — iframe loads the base
  `dashboard.html#<id>`; the module's own JS reads `location.hash` and renders
  that sub-view. Lowest-friction: single HTML file, no build changes.

**Fallback / backward-compat:** modules with no `tabs` behave exactly as today
— single `dashboard.html`, empty tab row. Nothing existing breaks.

**Remote modules:** `tabs[].entry` maps onto the module-federation `exposed`
entries the same way `remote_dashboard` does today; hash-mode tabs append
`#<id>` to the remote entry.

**Host wiring:**
- `ModuleSummary` gains `tabs: ModuleTab[]` (`{ id, label, entry? }`), parsed in
  `summarize()` in `stores/modules.ts`.
- Modules store gains `activeModuleTab: string | null` + `setModuleTab(id)`;
  picking a module resets to `tabs[0]?.id`; `closeDashboard()` clears it.
- `ModuleDashboardView` computes `iframeSrc` from the active tab (entry file or
  base + `#id`) and reloads/updates the iframe on tab change. The existing
  `useModuleBridge` protocol is unchanged. `atria:module:title` events keep
  working per tab.

## State & Wiring

- **`stores/modules.ts`:** `ModuleSummary.tabs`; new `activeModuleTab`,
  `setModuleTab(id)`; `openDashboard(name)` resets tab to `tabs[0]?.id`;
  `closeDashboard()` clears `activeModuleTab`.
- **`stores/chat.ts`:** existing `sidebarCollapsed` / mobile-drawer flags now
  drive the chat rail (intent rename, no new machinery).

**Component inventory:**
- *New:* `ChatRail`, `ModuleBreadcrumb` (+ picker dropdown), `ModuleTabs`,
  `BlackboardEntry` topbar control.
- *Modified:* `AppShell` (three-column body), `TopBar` (swap `ViewSwitcher` →
  breadcrumb/tabs/blackboard), `ChatPage` (drop center-swap; compose rail +
  module center + artifacts), `ModuleDashboardView` (tab-aware `iframeSrc`),
  `stores/modules.ts`.
- *Reused as-is:* `ChatInterface`, `ArtifactViewer`, `ResizeHandle`,
  `TenantSwitcher`, `MobileTabBar` (one added panel), settings/account menus.
- *Retired from chrome:* `ViewSwitcher` (logic folds into breadcrumb +
  blackboard entry); `ProjectSidebar` "Modules" list (moves to breadcrumb
  dropdown).

**Routing:** unchanged. `/chat` hosts the shell; `/blackboard` reached via the
top-bar entry. No new routes.

**Motion polish (non-destructive, respects existing tokens):** spring-physics
active underline on `ModuleTabs`, staggered reveal on the module-picker
dropdown, subtle press/hover on the rail collapse control — all using Atria's
existing motion primitives, not a new design language.

## Testing (both required per CLAUDE.md)

**Unit (`uv run pytest` / vitest for stores):**
- `stores/modules` tab parsing, `activeModuleTab` reset on module switch,
  no-tabs fallback.
- `ModuleTabs` render (active underline, empty when no tabs).
- Breadcrumb picker selection.

**E2E with real API (`OPENAI_API_KEY`, `make run`):**
- Chat works in the left rail.
- Breadcrumb switches modules.
- Tabs switch the center iframe (both entry-file and hash modes via a test
  module).
- Rail collapse reclaims width.
- Artifact panel still slides in on file open.
- Blackboard entry navigates.

## Out of Scope (YAGNI)

- Minder-specific styling/content or a full visual reskin.
- Per-tab deep-link URLs / route refactor (that was the rejected Approach C).
- Changes to the module bridge protocol.
- A purpose-built compact chat component (rejected Approach B — reuse
  `ChatInterface`).
