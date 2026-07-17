import { useEffect, useState } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';
import { api } from '../api';

// G01: shows the agent's next-step suggestion for the operator's current job.
export default function GuidanceBanner({ apiBase, jobId, sopId }: { apiBase: string; jobId: number; sopId: number }) {
  const { tokens } = useMinderTheme();
  const [msg, setMsg] = useState<string>('');
  useEffect(() => {
    api<{ output: string }>(apiBase, `/connector/tools/guide_next_step`, {
      method: 'POST', body: JSON.stringify({ arguments: { job_id: jobId, sop_id: sopId } }),
    }).then((r) => setMsg(typeof r.output === 'string' ? r.output : '')).catch(() => {});
  }, [apiBase, jobId, sopId]);
  if (!msg) return null;
  return (
    <div style={{ background: `${tokens.primary}18`, border: `1px solid ${tokens.primary}`, borderRadius: 10, padding: '10px 14px', margin: '0 0 12px', color: tokens.text, fontSize: 13 }}>
      <b style={{ color: tokens.primary }}>Gợi ý:</b> {msg}
    </div>
  );
}
