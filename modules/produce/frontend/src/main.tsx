import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import Dashboard from './dashboard';
import { TABS } from './dashboard.tabs';

// Standalone: same-origin API (backend serves this dist), dark theme by default.
// `standalone` shows the built-in persona switcher; embedded in the Minder host,
// the host top bar provides the tabs so it stays hidden.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Dashboard apiBase="" activeTab={TABS[0].id} theme="dark" agentEnabled={false} standalone />
  </StrictMode>,
);
