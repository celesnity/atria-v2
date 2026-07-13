import { useEffect, useState, type ReactNode } from "react";
import {
  MinderThemeProvider,
  useMinderTheme,
  AgentDriverProvider,
  type DashboardProps,
  type DashboardComponent,
} from "minder-ui-sdk";
import { ToastProvider } from "./ui/Toast";
import StatHeader from "./ui/StatHeader";
import ProductsPanel from "./panels/ProductsPanel";
import JobsPanel from "./panels/JobsPanel";
import MediaPanel from "./panels/MediaPanel";
import DataPanel from "./panels/DataPanel";
import MetricsPanel from "./panels/MetricsPanel";
import { TABS } from "./dashboard.tabs";

const PANELS: Record<string, React.ComponentType<{ apiBase: string }>> = {
  products: ProductsPanel,
  jobs: JobsPanel,
  media: MediaPanel,
  data: DataPanel,
  metrics: MetricsPanel,
};

/** Map an agent `navigate(route)` intent to a dashboard tab id. */
const ROUTE_TO_TAB: Record<string, string> = { products: "products" };

function Surface({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <div
      data-minder-dashboard=""
      style={{ minHeight: "100%", background: tokens.bg, color: tokens.text, fontFamily: "system-ui, -apple-system, sans-serif" }}
    >
      {children}
    </div>
  );
}

/**
 * Co-pilot-aware dashboard. Beyond the host-owned tab row, it wraps everything in
 * an `AgentDriverProvider` so the agent's UI intents drive the real components:
 * a `navigate` intent switches the panel, and `fill`/`focus`/`request_confirm`
 * reach the Add Product form via `useAgentForm`. Subscribes to the demo session
 * "default" (the bus the `assist_add_product` tool pushes to).
 */
function Dashboard({ apiBase, activeTab, theme }: DashboardProps) {
  const [tab, setTab] = useState<string>(activeTab ?? TABS[0].id);
  useEffect(() => {
    if (activeTab) setTab(activeTab);
  }, [activeTab]);

  const Panel = PANELS[tab] ?? PANELS[TABS[0].id];

  return (
    <MinderThemeProvider theme={theme}>
      <AgentDriverProvider apiBase={apiBase} onNavigate={(route) => setTab(ROUTE_TO_TAB[route] ?? route)}>
        <ToastProvider>
          <Surface>
            <StatHeader apiBase={apiBase} />
            <Panel apiBase={apiBase} />
          </Surface>
        </ToastProvider>
      </AgentDriverProvider>
    </MinderThemeProvider>
  );
}

const withMeta = Dashboard as DashboardComponent;
withMeta.meta = {
  title: "Module Template · SDK showcase",
  tabs: TABS.map((t) => ({ id: t.id, label: t.label, icon: t.icon })),
};

export default withMeta;
