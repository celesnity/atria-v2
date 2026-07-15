import { useEffect, useState, type ReactNode } from 'react';
import { MinderThemeProvider, useMinderTheme, type DashboardProps } from 'minder-ui-sdk';
import { ToastProvider } from './ui/Toast';
import { TABS } from './dashboard.tabs';
import OperatorRoute from './routes/operator';
import LeaderRoute from './routes/leader';
import SupervisorRoute from './routes/supervisor';
import ManagerRoute from './routes/manager';
import AdminRoute from './routes/admin';

const ROUTES: Record<string, React.ComponentType<{ apiBase: string }>> = {
  operator: OperatorRoute,
  leader: LeaderRoute,
  supervisor: SupervisorRoute,
  manager: ManagerRoute,
  admin: AdminRoute,
};

function TabBar({ tab, setTab }: { tab: string; setTab: (t: string) => void }) {
  const { tokens } = useMinderTheme();
  return (
    <div style={{ display: 'flex', gap: 4, padding: '10px 16px', borderBottom: `1px solid ${tokens.border}`, background: tokens.surfaceAlt }}>
      {TABS.map((t) => (
        <button
          key={t.id}
          onClick={() => setTab(t.id)}
          style={{
            background: tab === t.id ? tokens.primary : 'transparent',
            color: tab === t.id ? '#fff' : tokens.textMuted,
            border: 'none', borderRadius: 8, padding: '6px 14px', fontSize: 13, fontWeight: 500, cursor: 'pointer',
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Surface({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return (
    <div data-produce-dashboard="" style={{ minHeight: '100%', background: tokens.bg, color: tokens.text, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {children}
    </div>
  );
}

export default function Dashboard({ apiBase, activeTab, theme }: DashboardProps) {
  const [tab, setTab] = useState<string>(activeTab ?? TABS[0].id);
  useEffect(() => { if (activeTab) setTab(activeTab); }, [activeTab]);
  const Route = ROUTES[tab] ?? ROUTES.operator;
  return (
    <MinderThemeProvider theme={theme}>
      <ToastProvider>
        <Surface>
          <TabBar tab={tab} setTab={setTab} />
          <div style={{ padding: 16 }}>
            <Route apiBase={apiBase} />
          </div>
        </Surface>
      </ToastProvider>
    </MinderThemeProvider>
  );
}
