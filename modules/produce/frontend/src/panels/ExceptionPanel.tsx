import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function ExceptionPanel({ apiBase, mode = 'triage' }: { apiBase: string; mode?: 'triage' | 'escalated' }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [reason, setReason] = useState('thiếu vật tư');

  const open = useApi<Array<Record<string, unknown>>>(apiBase, `/exception/line/${lineId}/open`, [lineId]);
  const escalated = useApi<Array<Record<string, unknown>>>(apiBase, '/exception/escalated');
  const active = mode === 'escalated' ? escalated : open;

  const run = async (label: string, fn: () => Promise<unknown>) => {
    try { await fn(); active.reload(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const cols = [
    { key: 'id', label: 'ID' }, { key: 'reason', label: 'Lý do' }, { key: 'category', label: 'Loại' }, { key: 'status', label: 'Trạng thái' }, { key: 'opened_at', label: 'Mở lúc' },
    { key: 'act', label: '', render: (r: Record<string, unknown>) => (
      <div style={{ display: 'flex', gap: 6 }}>
        {mode === 'triage' && <Button variant="ghost" onClick={() => run('Đã phân loại', () => api(apiBase, `/exception/exceptions/${r.id}/triage`, { method: 'POST', body: JSON.stringify({ category: 'material' }) }))}>Triage</Button>}
        {mode === 'triage' && <Button variant="ghost" onClick={() => run('Đã escalate', () => api(apiBase, `/exception/exceptions/${r.id}/escalate`, { method: 'POST' }))}>Escalate</Button>}
        <Button variant="ghost" onClick={() => run('Đã đóng', () => api(apiBase, `/exception/exceptions/${r.id}/resolve`, { method: 'POST' }))}>Resolve</Button>
      </div>
    ) },
  ];

  return (
    <Section
      title={mode === 'escalated' ? 'Ngoại lệ đã escalate' : `Ngoại lệ mở · line ${lineId}`}
      actions={mode === 'triage'
        ? <><Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field><Field label="Lý do"><TextInput value={reason} onChange={setReason} /></Field><Button onClick={() => run('Đã raise', () => api(apiBase, '/exception/exceptions', { method: 'POST', body: JSON.stringify({ line_id: lineId, reason }) }))}>Raise</Button></>
        : undefined}
    >
      <DataTable columns={cols} rows={active.data ?? []} empty="Không có ngoại lệ" />
    </Section>
  );
}
