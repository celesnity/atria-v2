import { useEffect, useState } from 'react';

interface DashboardProps {
  /** Connector public base, e.g. http://localhost:9200 — passed by the host. */
  apiBase: string;
}

interface HealthState {
  ok: boolean;
  module?: string;
}

/**
 * The maintenance_copilot dashboard, rendered natively inside the Atria host
 * via Module Federation (no iframe). Starts minimal: a live health panel + a
 * grounded-query box hitting the connector's /connector/run 'retrieve' action.
 */
export default function DashboardApp({ apiBase }: DashboardProps) {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [q, setQ] = useState('');
  const [answer, setAnswer] = useState<string>('');

  useEffect(() => {
    fetch(`${apiBase}/connector/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ ok: false }));
  }, [apiBase]);

  async function retrieve() {
    const r = await fetch(`${apiBase}/connector/run`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ action: 'retrieve', args: { query: q } }),
    });
    const card = await r.json();
    setAnswer(card.answer ?? '(no answer)');
  }

  return (
    <div style={{ padding: 16 }}>
      <h2>Maintenance Copilot</h2>
      <p>Service: {health ? (health.ok ? 'online' : 'offline') : 'checking…'}</p>
      <input value={q} onChange={(e) => setQ(e.target.value)}
             placeholder="Ask a maintenance question…" style={{ width: '70%' }} />
      <button onClick={retrieve} disabled={!q.trim()}>Retrieve</button>
      {answer && <pre style={{ whiteSpace: 'pre-wrap' }}>{answer}</pre>}
    </div>
  );
}
