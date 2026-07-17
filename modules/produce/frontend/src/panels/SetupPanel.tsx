import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function SetupPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [toPart, setToPart] = useState(1);

  const open = useApi<Array<Record<string, unknown>>>(apiBase, `/setup/line/${lineId}/open`, [lineId]);
  const run = async (label: string, fn: () => Promise<unknown>) => {
    try { await fn(); open.reload(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const start = () => run('Đã bắt đầu changeover', () => api(apiBase, '/setup/changeovers', { method: 'POST', body: JSON.stringify({ line_id: lineId, to_part_id: toPart, checklist: [{ name: 'thay khuôn', done: false }, { name: 'chỉnh cữ', done: false }] }) }));

  return (
    <Section title={`Changeover · line ${lineId}`} actions={
      <>
        <Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>
        <Field label="Part mới"><NumberInput value={toPart} onChange={setToPart} /></Field>
        <Button onClick={start}>Bắt đầu</Button>
      </>
    }>
      <DataTable
        columns={[
          { key: 'id', label: 'ID' }, { key: 'to_part_id', label: 'Part mới' }, { key: 'started_at', label: 'Bắt đầu' },
          { key: 'act', label: '', render: (r) => (
            <div style={{ display: 'flex', gap: 6 }}>
              <Button variant="ghost" onClick={() => run('Đã hoàn tất', () => api(apiBase, `/setup/changeovers/${r.id}/complete`, { method: 'POST' }))}>Complete</Button>
              <Button variant="ghost" onClick={() => run('First-piece đạt', () => api(apiBase, `/setup/changeovers/${r.id}/first-piece`, { method: 'POST', body: JSON.stringify({ passed: true }) }))}>First-piece ✓</Button>
            </div>
          ) },
        ]}
        rows={open.data ?? []}
        empty="Không có changeover mở"
      />
    </Section>
  );
}
