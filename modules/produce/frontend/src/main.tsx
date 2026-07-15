import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './dashboard';
import { TABS } from './dashboard.tabs';

// Standalone: same-origin API (backend serves this dist), dark theme by default.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Dashboard apiBase="" activeTab={TABS[0].id} theme="dark" agentEnabled={false} />
  </StrictMode>,
);
