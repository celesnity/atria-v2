import { useEffect, useState, type ReactNode, type CSSProperties } from 'react';
import {
  MinderThemeProvider,
  useMinderTheme,
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
      [data-produce-dashboard]{ font-variant-numeric: tabular-nums; }
      .pr-card{ transition: box-shadow .25s ease, border-color .25s ease; }
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
    '--pr-card-hover-shadow': tokens.cardHoverShadow,
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
      <div style={{ maxWidth: 1080, margin: '0 auto', padding: '24px 24px 44px' }}>{children}</div>
    </div>
  );
}

// Standalone-only persona switcher (a refined segmented pill). Embedded in the
// Minder host, the host top bar already provides the persona tabs and passes
// `activeTab`, so this stays hidden — no duplicate header.
function PersonaSwitch({ tab, setTab }: { tab: string; setTab: (t: string) => void }) {
  const { tokens } = useMinderTheme();
  return (
    <div
      style={{
        display: 'inline-flex',
        gap: 2,
        padding: 4,
        marginBottom: 20,
        background: tokens.surfaceAlt,
        border: `1px solid ${tokens.border}`,
        borderRadius: 999,
      }}
    >
      {TABS.map((t) => (
        <button
          key={t.id}
          className="pr-btn"
          onClick={() => setTab(t.id)}
          style={{
            background: tab === t.id ? tokens.primary : 'transparent',
            color: tab === t.id ? '#fff' : tokens.textMuted,
            border: 'none',
            borderRadius: 999,
            padding: '6px 16px',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
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
      <MinderThemeProvider theme={theme}>
        <ToastProvider>{body}</ToastProvider>
      </MinderThemeProvider>
    );
  }

  // Agent path: wrap the same subtree in the co-work providers (additive).
  return (
    <MinderThemeProvider theme={theme}>
      <ToastProvider>
        <AgentDriverProvider apiBase={connectorBase}>
          <AgentRegistryProvider apiBase={connectorBase}>{body}</AgentRegistryProvider>
        </AgentDriverProvider>
      </ToastProvider>
    </MinderThemeProvider>
  );
}
