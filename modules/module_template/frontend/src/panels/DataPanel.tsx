import { useEffect, useState } from 'react';

export function DataPanel({ apiBase }: { apiBase: string }) {
  const [ov, setOv] = useState<any>({});
  useEffect(() => { fetch(`${apiBase}/connector/overview`).then(r => r.json()).then(setOv).catch(() => {}); }, [apiBase]);
  return (
    <div>
      <h3>Data</h3>
      <p>mt_jobs: {ov.mt_jobs ?? '…'} · mt_media: {ov.mt_media ?? '…'} · atria artifacts: {ov.atria_artifacts_count ?? '…'}</p>
      <h4>Atria conversations (read-only)</h4>
      <ul>{(ov.atria_conversations || []).map((c: any) => <li key={c.id}>#{c.id} {c.title || '(untitled)'} — {c.status}</li>)}</ul>
    </div>
  );
}
