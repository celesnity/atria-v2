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
  const [mrStation, setMrStation] = useState(1);
  const [mrPart, setMrPart] = useState('');
  const [mrQty, setMrQty] = useState(1);
  const [mrBy, setMrBy] = useState('');

  const open = useApi<Array<Record<string, unknown>>>(apiBase, `/exception/line/${lineId}/open`, [lineId]);
  const escalated = useApi<Array<Record<string, unknown>>>(apiBase, '/exception/escalated');
  const materialRequests = useApi<Array<Record<string, unknown>>>(apiBase, '/exception/material-requests');
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
      {mode === 'triage' && (
        <Section
          title="Yêu cầu vật tư"
          actions={
            <>
              <Field label="Trạm"><NumberInput value={mrStation} onChange={setMrStation} /></Field>
              <Field label="Mã vật tư"><TextInput value={mrPart} onChange={setMrPart} /></Field>
              <Field label="Số lượng"><NumberInput value={mrQty} onChange={setMrQty} /></Field>
              <Field label="Người yêu cầu"><TextInput value={mrBy} onChange={setMrBy} /></Field>
              <Button onClick={() => run('Đã yêu cầu vật tư', async () => { await api(apiBase, '/exception/material-requests', { method: 'POST', body: JSON.stringify({ station_id: mrStation, part_code: mrPart, qty: mrQty, requested_by: mrBy }) }); materialRequests.reload(); })}>Yêu cầu</Button>
            </>
          }
        >
          <DataTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'station_id', label: 'Trạm' },
              { key: 'part_code', label: 'Mã vật tư' },
              { key: 'qty', label: 'Số lượng' },
              { key: 'status', label: 'Trạng thái' },
            ]}
            rows={materialRequests.data ?? []}
            empty="Không có yêu cầu vật tư"
          />
        </Section>
      )}
    </Section>
  );
}
