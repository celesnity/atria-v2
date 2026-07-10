import { useEffect, useState } from 'react';

const TOOLS = [
  'template_typed_query', 'template_card', 'template_block', 'template_stream',
  'template_secure', 'template_async_job', 'template_export',
];

export default function DashboardApp({ apiBase }: { apiBase: string }) {
  const [pong, setPong] = useState<string>('…');
  useEffect(() => {
    fetch(`${apiBase}/connector/ping`).then(r => r.json())
      .then(d => setPong(d.pong ?? 'unknown')).catch(() => setPong('offline'));
  }, [apiBase]);
  return (
    <div style={{ padding: 16, fontFamily: 'system-ui' }}>
      <h2>module_template — SDK showcase</h2>
      <p>Connector: <code>{apiBase}</code> · /ping → <b>{pong}</b></p>
      <p>Ask the agent to run any of these tools to see the SDK feature it demos:</p>
      <ul>{TOOLS.map(t => <li key={t}><code>{t}</code></li>)}</ul>
    </div>
  );
}
