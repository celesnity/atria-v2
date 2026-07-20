import { useReducer, useState, type ReactNode } from 'react';
import { EmbinderProvider, useEmbinder } from '@embinder/react';
import { Agent, AgentRegistryProvider, MinderThemeProvider, useMinderTheme, type DashboardComponent, type DashboardProps } from './embinder';
import { IncidentAnalystPage } from './platform/IncidentAnalystPage';
import { MissionControlPage } from './platform/MissionControlPage';
import { PlatformShell } from './platform/PlatformShell';
import { initialPlatformState, platformReducer } from './platform/store';
import type { PlatformPage } from './platform/types';
import Mascot from './ui/Mascot';
import { ToastProvider } from './ui/Toast';

function Surface({ children }: { children: ReactNode }) {
  const { tokens } = useMinderTheme();
  return <main data-minder-dashboard="" style={{ minHeight: '100%', padding: 24, background: tokens.bg, color: tokens.text, fontFamily: 'system-ui, -apple-system, sans-serif' }}>{children}</main>;
}

/** A UI-only federation surface; Minder owns all chat and agent execution. */
function Dashboard({ theme }: DashboardProps) {
  const [state, dispatch] = useReducer(platformReducer, initialPlatformState);
  const [activePage, setActivePage] = useState<PlatformPage>('mission-control');
  const incident = state.incidents.find((item) => item.id === state.selectedIncidentId)!;
  const analysis = useEmbinder({
    name: 'analyze_incident',
    description: 'Analyze the simulated incident currently selected in the operations platform.',
    context: () => ({ incident: incident.id, risk: incident.risk, status: incident.status }),
    handler: () => { dispatch({ type: 'analyze_incident' }); return { ok: true, incident: incident.id, risk: 41, finding: 'Traffic anomaly isolated' }; },
  });
  const approve = useEmbinder({
    name: 'approve_escalation',
    description: 'Approve the pending mitigation escalation. This action requires human approval.',
    destructive: true,
    context: () => ({ incident: incident.id, pending: state.workflow.status === 'pending_approval' }),
    handler: () => { dispatch({ type: 'approve_escalation' }); return { ok: true, incident: incident.id, status: 'approved' }; },
  });
  const page = activePage === 'mission-control'
    ? <MissionControlPage state={state} dispatch={dispatch} />
    : activePage === 'incident-analyst'
      ? <IncidentAnalystPage state={state} dispatch={dispatch} />
      : <section><h1>{activePage === 'workflow-approvals' ? 'Workflow & Approvals' : 'Activity & Audit'}</h1><p style={{ color: '#9ca8c8' }}>This surface is being connected to the shared platform state.</p></section>;

  return <MinderThemeProvider theme={theme}><EmbinderProvider url="ws://localhost:7331/app" viz chat={false}><AgentRegistryProvider><ToastProvider><Surface><Agent.Page name="module_template" description="Embind UI-only operations platform"><section style={{ maxWidth: 1280 }}><Agent.Data name="runtime" description="The static module platform state and its current agent-operable surface." value={{ runtime: 'ui-only', chat: 'minder', cursor: 'embinder', activePage, incident: incident.id, risk: incident.risk, workflow: state.workflow.status }}><PlatformShell activePage={activePage} onNavigate={setActivePage}>{page}</PlatformShell></Agent.Data></section></Agent.Page></Surface><Mascot /></ToastProvider></AgentRegistryProvider></EmbinderProvider></MinderThemeProvider>;
}

const withMeta = Dashboard as DashboardComponent;
withMeta.meta = { title: 'Module Template · Embinder', tabs: [] };

export default withMeta;
