import type { ReactNode } from 'react';
import type { PlatformPage } from './types';

const pages: Array<{ id: PlatformPage; label: string; note: string }> = [
  { id: 'mission-control', label: 'Mission Control', note: 'Live overview' },
  { id: 'incident-analyst', label: 'Incident & Data Analyst', note: 'Analyze signals' },
  { id: 'workflow-approvals', label: 'Workflow & Approvals', note: 'Decision queue' },
  { id: 'activity-audit', label: 'Activity & Audit', note: 'Trace actions' },
];

export function PlatformShell({ activePage, onNavigate, children }: { activePage: PlatformPage; onNavigate: (page: PlatformPage) => void; children: ReactNode }) {
  return <div style={{ display: 'grid', gridTemplateColumns: '230px minmax(0, 1fr)', gap: 24, minHeight: 640 }}>
    <aside style={{ border: '1px solid #2b3758', background: '#11182c', borderRadius: 16, padding: 14 }}>
      <div style={{ padding: '8px 10px 20px' }}><div style={{ color: '#9ca8c8', fontSize: 11, letterSpacing: '0.12em', fontWeight: 800 }}>EMBINDER DEMO</div><strong style={{ display: 'block', marginTop: 5, fontSize: 18 }}>Operations Platform</strong></div>
      <nav aria-label="Platform pages" style={{ display: 'grid', gap: 6 }}>{pages.map((page) => {
        const active = page.id === activePage;
        return <button key={page.id} type="button" onClick={() => onNavigate(page.id)} aria-current={active ? 'page' : undefined} style={{ textAlign: 'left', padding: '11px 10px', border: active ? '1px solid #477cf6' : '1px solid transparent', borderRadius: 10, cursor: 'pointer', color: active ? '#fff' : '#c5cde5', background: active ? 'linear-gradient(135deg, #2e6bf6, #5145a5)' : 'transparent' }}><span style={{ display: 'block', fontWeight: 750, fontSize: 13 }}>{page.label}</span><span style={{ display: 'block', marginTop: 3, color: active ? '#dbe5ff' : '#7885a8', fontSize: 11 }}>{page.note}</span></button>;
      })}</nav>
    </aside>
    <section style={{ minWidth: 0 }}>{children}</section>
  </div>;
}
