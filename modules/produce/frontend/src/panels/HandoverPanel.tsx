import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function HandoverPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [fromShift, setFromShift] = useState(1);
  const [output, setOutput] = useState(0);

  const current = useApi<Record<string, unknown> | null>(apiBase, `/handover/shifts/${fromShift}`, [fromShift]);
  const run = async (label: string, fn: () => Promise<unknown>) => {
    try { await fn(); current.reload(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const create = () => run('Đã tạo bàn giao', () => api(apiBase, '/handover/records', { method: 'POST', body: JSON.stringify({ line_id: lineId, from_shift_id: fromShift, output_count: output }) }));
  const h = current.data;

  return (
    <Section title="Bàn giao ca" actions={
      <>
        <Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>
        <Field label="Ca ra"><NumberInput value={fromShift} onChange={setFromShift} /></Field>
        <Field label="Sản lượng"><NumberInput value={output} onChange={setOutput} /></Field>
        <Button onClick={create}>Tạo</Button>
      </>
    }>
      {h ? (
        <div style={{ fontSize: 13, lineHeight: 1.8 }}>
          <div>Sản lượng: <b>{String(h.output_count)}</b></div>
          <div>Việc treo: <b>{(h.pending as unknown[])?.length ?? 0}</b> · Downtime mở: <b>{(h.open_downtime as unknown[])?.length ?? 0}</b></div>
          <div>Đã đọc: <b>{h.acknowledged_at ? String(h.acknowledged_at) : 'chưa'}</b></div>
          {!h.acknowledged_at && <Button onClick={() => run('Đã xác nhận đọc', () => api(apiBase, `/handover/records/${h.id}/acknowledge`, { method: 'POST' }))}>Xác nhận đã đọc</Button>}
        </div>
      ) : <p style={{ fontSize: 13, color: '#888' }}>Chưa có bàn giao cho ca này.</p>}
    </Section>
  );
}
