import { useEffect, useState, type ReactNode, type CSSProperties } from 'react';
import '@mantine/core/styles.css';
import '@mantine/charts/styles.css';
import { MantineProvider, SegmentedControl } from '@mantine/core';
import { QueryClientProvider } from '@tanstack/react-query';
import { produceTheme } from './theme.mantine';
import { queryClient } from './lib/queryClient';
import {
  MinderThemeProvider,
  useMinderTheme,
  MinderPopupProvider,
  AgentDriverProvider,
  AgentRegistryProvider,
  type DashboardProps,
} from 'minder-ui-sdk';
import { ToastProvider } from './ui/Toast';
import { TABS } from './dashboard.tabs';
import OperatorRoute from './routes/operator';
import LeaderRoute from './routes/leader';
import SupervisorRoute from './routes/supervisor';
import ManagerRoute from './routes/manager';
import AdminRoute from './routes/admin';
import GuidanceBanner from './agent/GuidanceBanner';
import DecisionSurface from './agent/DecisionSurface';

const ROUTES: Record<string, React.ComponentType<{ apiBase: string }>> = {
  operator: OperatorRoute,
  leader: LeaderRoute,
  supervisor: SupervisorRoute,
  manager: ManagerRoute,
  admin: AdminRoute,
};

// Interactive states (hover / focus / row-hover) + numeric alignment, keyed off
// CSS variables the Surface sets from the active Celesnity theme, so they stay
// theme-aware without per-element JS listeners.
function GlobalStyle() {
  return (
    <style>{`
      /* ── Produce dashboard — high-end custom polish ──────────────────
         Soft Structuralism: diffused ambient elevation, "double-bezel"
         glass-in-tray card highlights, spring-physics micro-interactions.
         All motion rides transform/opacity on a custom cubic-bezier; every
         accent derives from the live Celesnity token so it stays theme-aware. */

      [data-produce-dashboard]{
        --pr-spring: cubic-bezier(0.32, 0.72, 0, 1);
        font-variant-numeric: tabular-nums;
        font-feature-settings: "cv01","ss01","tnum";
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
        position: relative;
        isolation: isolate;
      }

      /* Ambient mesh-gradient wash — two faint accent orbs behind the grid
         for cinematic depth. Static + pointer-events:none = zero repaint cost. */
      [data-produce-dashboard]::before{
        content: '';
        position: absolute; inset: 0; z-index: 0; pointer-events: none;
        background:
          radial-gradient(680px 460px at 8% -6%, color-mix(in srgb, var(--pr-accent) 12%, transparent), transparent 70%),
          radial-gradient(560px 420px at 104% 2%, color-mix(in srgb, var(--pr-accent) 7%, transparent), transparent 72%);
      }
      /* Content floats above the wash and gently rises in on mount (once). */
      [data-produce-dashboard] > div{ position: relative; z-index: 1; animation: pr-rise .62s var(--pr-spring) both; }
      @keyframes pr-rise{ from{ opacity: 0; transform: translateY(14px); } to{ opacity: 1; transform: none; } }

      /* Cards — machined "glass plate in a tray": soft diffused shadow +
         an inset top highlight ::after so the surface catches light. */
      [data-produce-dashboard] .mantine-Card-root{
        position: relative;
        transition: box-shadow .5s var(--pr-spring), border-color .5s var(--pr-spring), transform .5s var(--pr-spring);
        box-shadow: 0 1px 2px rgba(28,34,64,.05), 0 10px 30px -16px rgba(28,34,64,.22);
      }
      [data-produce-dashboard] .mantine-Card-root::after{
        content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.65), inset 0 0 0 1px rgba(255,255,255,.03);
      }
      [data-produce-dashboard] .mantine-Card-root:hover{
        transform: translateY(-3px);
        border-color: color-mix(in srgb, var(--pr-accent) 34%, var(--pr-border));
        box-shadow: 0 2px 4px rgba(28,34,64,.06), 0 22px 46px -18px color-mix(in srgb, var(--pr-accent) 38%, rgba(28,34,64,.5));
      }
      [data-produce-dashboard] .pr-interactive{ cursor: pointer; }

      /* Buttons — spring press + inset sheen on filled, quiet lift on the rest. */
      [data-produce-dashboard] .mantine-Button-root{
        transition: transform .4s var(--pr-spring), box-shadow .4s var(--pr-spring), background .2s ease, filter .2s ease;
      }
      [data-produce-dashboard] .mantine-Button-root:active:not(:disabled){ transform: scale(.97); }
      [data-produce-dashboard] .mantine-Button-filled{ box-shadow: 0 1px 2px rgba(37,89,230,.28), inset 0 1px 0 rgba(255,255,255,.28); }
      [data-produce-dashboard] .mantine-Button-filled:hover:not(:disabled){
        box-shadow: 0 6px 18px -4px color-mix(in srgb, var(--pr-accent) 55%, transparent), inset 0 1px 0 rgba(255,255,255,.34);
      }

      /* Inputs — refined accent-glow focus ring (soft, not harsh outline). */
      [data-produce-dashboard] .mantine-Input-input{ transition: border-color .18s ease, box-shadow .18s ease; }
      [data-produce-dashboard] .mantine-Input-input:focus,
      [data-produce-dashboard] .mantine-Input-input:focus-within{
        border-color: var(--pr-accent);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--pr-accent) 18%, transparent);
      }

      /* Table rows — smooth accent-tinted hover. */
      [data-produce-dashboard] tbody tr{ transition: background .16s ease; }
      [data-produce-dashboard] tbody tr:hover{ background: color-mix(in srgb, var(--pr-accent) 6%, transparent) !important; }

      /* Segmented persona switcher — glass pill treatment. */
      [data-produce-dashboard] .mantine-SegmentedControl-root{ box-shadow: inset 0 1px 2px rgba(28,34,64,.06); }
      [data-produce-dashboard] .mantine-SegmentedControl-indicator{ box-shadow: 0 2px 8px -2px color-mix(in srgb, var(--pr-accent) 40%, transparent); }

      /* Crisp cool scrollbars + branded selection. */
      [data-produce-dashboard] ::-webkit-scrollbar{ width: 10px; height: 10px; }
      [data-produce-dashboard] ::-webkit-scrollbar-thumb{ background: color-mix(in srgb, var(--pr-muted) 40%, transparent); border-radius: 999px; border: 2px solid transparent; background-clip: padding-box; }
      [data-produce-dashboard] ::-webkit-scrollbar-thumb:hover{ background: color-mix(in srgb, var(--pr-accent) 55%, transparent); background-clip: padding-box; }
      [data-produce-dashboard] ::selection{ background: color-mix(in srgb, var(--pr-accent) 22%, transparent); }

      /* ── Sub-navigation (splits a persona route into focused pages) ─────── */
      [data-produce-dashboard] .pr-subnav{
        display: flex; gap: 4px; flex-wrap: wrap; width: max-content; max-width: 100%;
        padding: 5px; border-radius: 16px;
        background: color-mix(in srgb, var(--pr-surface-alt) 70%, transparent);
        border: 1px solid var(--pr-border);
        box-shadow: inset 0 1px 2px rgba(28,34,64,.05);
      }
      [data-produce-dashboard] .pr-subnav-tab{
        display: inline-flex; align-items: center; gap: 8px;
        padding: 9px 15px; border: 0; background: transparent; cursor: pointer;
        border-radius: 12px; font: inherit; font-size: 13.5px; font-weight: 600;
        color: var(--pr-muted); letter-spacing: -.01em; white-space: nowrap;
        transition: color .25s var(--pr-spring), background .25s var(--pr-spring), box-shadow .25s var(--pr-spring), transform .18s var(--pr-spring);
      }
      [data-produce-dashboard] .pr-subnav-tab:hover{ color: var(--pr-text); background: color-mix(in srgb, var(--pr-text) 5%, transparent); }
      [data-produce-dashboard] .pr-subnav-tab.is-active{
        color: #fff;
        background: linear-gradient(135deg, var(--mantine-color-cobalt-5), var(--mantine-color-cobalt-7));
        box-shadow: 0 8px 18px -8px var(--mantine-color-cobalt-5), inset 0 1px 0 rgba(255,255,255,.28);
      }
      [data-produce-dashboard] .pr-subnav-tab:active{ transform: scale(.97); }
      [data-produce-dashboard] .pr-subnav-ico{ display: inline-flex; }
      [data-produce-dashboard] .pr-subnav-badge{
        display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 5px;
        border-radius: 999px; font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
        background: color-mix(in srgb, var(--pr-accent) 16%, transparent); color: var(--pr-accent);
      }
      [data-produce-dashboard] .pr-subnav-tab.is-active .pr-subnav-badge{ background: rgba(255,255,255,.22); color: #fff; }

      /* ── Hero briefing banner ──────────────────────────────────────────── */
      [data-produce-dashboard] .pr-hero{
        position: relative; overflow: hidden; color: #EAF1FF;
        border-radius: 20px; padding: 26px 28px;
        background: radial-gradient(130% 170% at 100% 0%, #2E6BF6 0%, #1E50D8 46%, #0E2A86 100%);
        border: 1px solid rgba(255,255,255,.12);
        box-shadow: 0 22px 46px -24px rgba(30,80,216,.7), inset 0 1px 0 rgba(255,255,255,.16);
      }
      [data-produce-dashboard] .pr-hero-glow{
        position: absolute; inset: 0; pointer-events: none;
        background:
          radial-gradient(420px 220px at 10% 130%, rgba(90,166,255,.5), transparent 70%),
          radial-gradient(300px 200px at 92% -30%, rgba(255,255,255,.18), transparent 70%);
      }
      [data-produce-dashboard] .pr-hero-body{ position: relative; display: flex; gap: 24px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
      [data-produce-dashboard] .pr-hero-eyebrow{ text-transform: uppercase; letter-spacing: .16em; font-size: 11px; font-weight: 700; color: rgba(234,241,255,.78); }
      [data-produce-dashboard] .pr-hero-title{ font-size: 26px; font-weight: 800; letter-spacing: -.02em; line-height: 1.12; color: #fff; }
      [data-produce-dashboard] .pr-hero-sub{ font-size: 14px; color: rgba(234,241,255,.82); margin-top: 6px; max-width: 48ch; }
      [data-produce-dashboard] .pr-hero-status{ border: 1px solid rgba(255,255,255,.2) !important; }
      [data-produce-dashboard] .pr-hero-dot{ display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 3px; vertical-align: middle; }
      [data-produce-dashboard] .pr-hero-dot[data-status="online"]{ background: #34D399; animation: pr-pulse 2.2s var(--pr-spring) infinite; }
      [data-produce-dashboard] .pr-hero-dot[data-status="idle"]{ background: #CBD5E1; }
      @keyframes pr-pulse{ 0%,100%{ box-shadow: 0 0 0 3px rgba(52,211,153,.28);} 50%{ box-shadow: 0 0 0 6px rgba(52,211,153,.05);} }
      [data-produce-dashboard] .pr-hero-metrics{ position: relative; display: flex; gap: 10px; flex-wrap: wrap; }
      [data-produce-dashboard] .pr-hero-metric{ min-width: 92px; padding: 12px 16px; border-radius: 14px; background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.18); }
      [data-produce-dashboard] .pr-hero-metric-value{ font-size: 24px; font-weight: 800; color: #fff; line-height: 1; font-variant-numeric: tabular-nums; }
      [data-produce-dashboard] .pr-hero-metric-label{ font-size: 11px; color: rgba(234,241,255,.74); text-transform: uppercase; letter-spacing: .06em; margin-top: 4px; }

      /* Tables — fluid width, cell text wraps; horizontal scroll is a contained,
         rounded fallback only when a table is genuinely too wide (no bleed past
         the card edge, no clipped first column). */
      [data-produce-dashboard] .pr-tablewrap{ width: 100%; overflow-x: auto; border-radius: 10px; }
      [data-produce-dashboard] .pr-tablewrap table{ width: 100%; }
      [data-produce-dashboard] .pr-tablewrap td{ overflow-wrap: anywhere; }
      [data-produce-dashboard] .pr-tablewrap::-webkit-scrollbar{ height: 8px; }
      [data-produce-dashboard] .pr-tablewrap::-webkit-scrollbar-thumb{ background: color-mix(in srgb, var(--pr-muted) 40%, transparent); border-radius: 999px; }

      /* Guide card — faint accent wash in the corner. */
      [data-produce-dashboard] .pr-guide{ position: relative; overflow: hidden; }
      [data-produce-dashboard] .pr-guide::before{
        content: ''; position: absolute; top: -30px; right: -30px; width: 120px; height: 120px; border-radius: 50%;
        background: radial-gradient(circle, color-mix(in srgb, var(--pr-accent) 12%, transparent), transparent 70%); pointer-events: none;
      }

      /* Legacy inline-styled hooks (kept for panels not yet on Mantine). */
      .pr-card{ transition: box-shadow .22s var(--pr-ease), border-color .22s var(--pr-ease); }
      .pr-card:hover{ box-shadow: var(--pr-card-hover-shadow); border-color: color-mix(in srgb, var(--pr-accent) 30%, var(--pr-border)); }
      .pr-btn{ transition: filter .18s ease, background .18s ease; }
      .pr-btn:hover:not(:disabled){ filter: brightness(1.08); }
      .pr-btn:focus-visible{ outline: 2px solid var(--pr-accent); outline-offset: 2px; }
      .pr-ghost:hover:not(:disabled){ background: color-mix(in srgb, var(--pr-text) 7%, transparent); }
      .pr-input{ transition: border-color .16s ease, box-shadow .16s ease; }
      .pr-input:focus{ outline: none; border-color: var(--pr-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--pr-accent) 20%, transparent); }
      .pr-input::placeholder{ color: var(--pr-muted); opacity: .55; }
      .pr-row{ transition: background .14s ease; }
      .pr-row:hover{ background: color-mix(in srgb, var(--pr-accent) 6%, transparent); }

      @media (prefers-reduced-motion: reduce){
        [data-produce-dashboard] *,
        [data-produce-dashboard] > div{ animation: none !important; transition: none !important; }
        [data-produce-dashboard] .mantine-Card-root:hover,
        [data-produce-dashboard] .pr-interactive:hover{ transform: none; }
      }
    `}</style>
  );
}

function Surface({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  const vars = {
    '--pr-accent': tokens.primary,
    '--pr-text': tokens.text,
    '--pr-muted': tokens.textMuted,
    '--pr-border': tokens.border,
    '--pr-surface': tokens.surface,
    '--pr-surface-alt': tokens.surfaceAlt,
    '--pr-card-hover-shadow': tokens.cardHoverShadow,
    '--pr-ease': 'cubic-bezier(0.22, 1, 0.36, 1)',
  } as CSSProperties;
  return (
    <div
      data-produce-dashboard=""
      style={{
        minHeight: '100%',
        background: tokens.bg,
        color: tokens.text,
        fontFamily:
          'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        ...vars,
      }}
    >
      <GlobalStyle />
      <div style={{ maxWidth: 1280, margin: '0 auto', padding: '28px 28px 56px' }}>{children}</div>
    </div>
  );
}

// Standalone-only persona switcher (a refined segmented pill). Embedded in the
// Minder host, the host top bar already provides the persona tabs and passes
// `activeTab`, so this stays hidden — no duplicate header.
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

export default function Dashboard({
  apiBase,
  activeTab,
  theme,
  agentEnabled = false,
  standalone = false,
}: DashboardProps & { agentEnabled?: boolean; standalone?: boolean }) {
  const [tab, setTab] = useState<string>(activeTab ?? TABS[0].id);
  useEffect(() => {
    if (activeTab) setTab(activeTab);
  }, [activeTab]);
  const Route = ROUTES[tab] ?? ROUTES.operator;
  const connectorBase = `${apiBase}/connector`;
  // Sync Mantine's color scheme with the Minder sky so its text/border/surface
  // CSS variables resolve correctly. Without this, Mantine stays light-scheme
  // and renders dark text (Title/Text/dimmed/labels) — invisible on the dark bg.
  const colorScheme: 'light' | 'dark' = theme === 'light' ? 'light' : 'dark';

  const body = (
    <Surface>
      {standalone ? <PersonaSwitch tab={tab} setTab={setTab} /> : null}
      {agentEnabled && tab === 'supervisor' ? <DecisionSurface apiBase={connectorBase} /> : null}
      {agentEnabled && tab === 'operator' ? (
        <GuidanceBanner apiBase={apiBase} jobId={1} sopId={1} />
      ) : null}
      <Route apiBase={apiBase} />
    </Surface>
  );

  // Non-agent path: byte-identical behavior to Track A.
  if (!agentEnabled) {
    return (
      <MantineProvider theme={produceTheme} forceColorScheme={colorScheme} cssVariablesSelector="[data-produce-dashboard]" getRootElement={() => (document.querySelector('[data-produce-dashboard]') as HTMLElement) ?? undefined}>
        <QueryClientProvider client={queryClient}>
          <MinderThemeProvider theme={theme}>
            <MinderPopupProvider scopeAttribute="data-produce-dashboard" colorScheme={colorScheme}>
              <ToastProvider>{body}</ToastProvider>
            </MinderPopupProvider>
          </MinderThemeProvider>
        </QueryClientProvider>
      </MantineProvider>
    );
  }

  // Agent path: wrap the same subtree in the co-work providers (additive).
  return (
    <MantineProvider theme={produceTheme} forceColorScheme={colorScheme} cssVariablesSelector="[data-produce-dashboard]" getRootElement={() => (document.querySelector('[data-produce-dashboard]') as HTMLElement) ?? undefined}>
      <QueryClientProvider client={queryClient}>
        <MinderThemeProvider theme={theme}>
          <MinderPopupProvider scopeAttribute="data-produce-dashboard" colorScheme={colorScheme}>
            <ToastProvider>
              <AgentDriverProvider apiBase={connectorBase}>
                <AgentRegistryProvider apiBase={connectorBase}>{body}</AgentRegistryProvider>
              </AgentDriverProvider>
            </ToastProvider>
          </MinderPopupProvider>
        </MinderThemeProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
