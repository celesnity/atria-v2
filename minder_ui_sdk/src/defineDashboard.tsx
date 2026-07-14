import type { ReactElement, ReactNode } from 'react';
import type { DashboardComponent, DashboardConfig, DashboardProps } from './types';
import { MinderThemeProvider, useMinderTheme } from './theme';

/** Themed backdrop for the whole dashboard — reads tokens from context. */
function ThemedSurface({ children }: { children: ReactNode }): ReactElement {
  const { tokens } = useMinderTheme();
  return (
    <div
      data-minder-dashboard=""
      style={{
        minHeight: '100%',
        background: tokens.bg,
        color: tokens.text,
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      {children}
    </div>
  );
}

/**
 * Build a module's federated `./Dashboard` from a tab config. The host owns the
 * tab row (top bar) and passes `activeTab` down; this shell renders the matching
 * panel (falling back to the first tab) plus an optional persistent header.
 *
 * The host also forwards its active sky as `theme` ('light' | 'dark'); the shell
 * publishes it (plus the token palette) via `MinderThemeProvider`, so the header
 * and panels read colors with `useMinderTheme()` instead of hardcoding them.
 */
export function defineDashboard(config: DashboardConfig): DashboardComponent {
  const firstId = config.tabs[0]?.id ?? null;

  function Dashboard({ apiBase, activeTab, theme }: DashboardProps): ReactElement {
    const id = activeTab && config.panels[activeTab] ? activeTab : firstId;
    const Panel = id ? config.panels[id] : undefined;
    const Header = config.header;
    return (
      <MinderThemeProvider theme={theme}>
        <ThemedSurface>
          {Header ? <Header apiBase={apiBase} /> : null}
          {Panel ? <Panel apiBase={apiBase} /> : null}
        </ThemedSurface>
      </MinderThemeProvider>
    );
  }

  const withMeta = Dashboard as DashboardComponent;
  withMeta.meta = {
    title: config.title,
    tabs: config.tabs.map((t) => ({ id: t.id, label: t.label, icon: t.icon })),
  };
  return withMeta;
}
