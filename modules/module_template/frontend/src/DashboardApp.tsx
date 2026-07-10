import { useState } from 'react';
import { JobsPanel } from './panels/JobsPanel';
import { MediaPanel } from './panels/MediaPanel';
import { DataPanel } from './panels/DataPanel';
import { MetricsPanel } from './panels/MetricsPanel';

const TABS = ['Jobs', 'Media', 'Data', 'Metrics'] as const;

export default function DashboardApp({ apiBase }: { apiBase: string }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Jobs');
  return (
    <div style={{ padding: 16, fontFamily: 'system-ui' }}>
      <h2>module_template — full-stack showcase</h2>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
                  style={{ fontWeight: tab === t ? 700 : 400 }}>{t}</button>
        ))}
      </div>
      {tab === 'Jobs' && <JobsPanel apiBase={apiBase} />}
      {tab === 'Media' && <MediaPanel apiBase={apiBase} />}
      {tab === 'Data' && <DataPanel apiBase={apiBase} />}
      {tab === 'Metrics' && <MetricsPanel apiBase={apiBase} />}
    </div>
  );
}
