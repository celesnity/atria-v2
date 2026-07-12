import type { ComponentType } from 'react';
import type { MinderTheme } from './theme';

/** Tab metadata — plain, JSON-serializable (id/label go to the host manifest). */
export interface TabMeta {
  id: string;
  label: string;
  icon?: string;
}

/** Props the Minder host passes to a module's federated `./Dashboard`. */
export interface DashboardProps {
  apiBase: string;
  activeTab?: string | null;
  /** Active Minder sky, forwarded by the host (defaults to 'dark'). */
  theme?: MinderTheme | null;
}

export interface DashboardConfig {
  title?: string;
  /** Persistent chrome above the active panel (stat cards, health, …). */
  header?: ComponentType<{ apiBase: string }>;
  /** Tab metadata — the single source of truth for tab identity/labels. */
  tabs: TabMeta[];
  /** Panel component per tab id. Keys must cover every tab id. */
  panels: Record<string, ComponentType<{ apiBase: string }>>;
}

export type DashboardComponent = ComponentType<DashboardProps> & {
  meta: { title?: string; tabs: TabMeta[] };
};
