import { useEffect, useState } from 'react';
import { BarChart } from '../Chart';

export function MetricsPanel({ apiBase }: { apiBase: string }) {
  const [m, setM] = useState<any>({});
  useEffect(() => { fetch(`${apiBase}/connector/metrics`).then(r => r.json()).then(setM).catch(() => {}); }, [apiBase]);
  const bars = Object.entries(m.jobs_by_status || {}).map(([label, value]) => ({ label, value: value as number }));
  return (
    <div>
      <h3>Metrics</h3>
      <h4>Jobs by status</h4>
      <BarChart data={bars.length ? bars : [{ label: 'none', value: 0 }]} />
      <p>Media stored: {((m.media_total_bytes || 0) / 1024).toFixed(1)} KB</p>
    </div>
  );
}
