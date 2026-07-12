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
