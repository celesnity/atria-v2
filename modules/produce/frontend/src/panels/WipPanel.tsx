import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

const STATION_STATES = ['idle', 'running', 'down', 'blocked', 'setup'];

export default function WipPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [taskId, setTaskId] = useState(1);
  const [jobId, setJobId] = useState(1);
  const [stationId, setStationId] = useState(1);
  const [qty, setQty] = useState(1);
  const [lot, setLot] = useState('');

  const total = useApi<{ total: number }>(apiBase, `/wip/stations/${stationId}/total`, [stationId]);
  const stStatus = useApi<Record<string, unknown> | null>(apiBase, `/wip/stations/${stationId}/status`, [stationId]);

  const run = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    try { await fn(); after?.(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  return (
    <>
      <Section title="Job" actions={
        <>
          <Field label="Task id"><NumberInput value={taskId} onChange={setTaskId} /></Field>
          <Button onClick={() => run('Đã start job', () => api(apiBase, '/wip/jobs', { method: 'POST', body: JSON.stringify({ task_id: taskId, station_id: stationId }) }))}>Start</Button>
          <Field label="Job id"><NumberInput value={jobId} onChange={setJobId} /></Field>
          <Button variant="ghost" onClick={() => run('Đã complete job', () => api(apiBase, `/wip/jobs/${jobId}/complete`, { method: 'POST' }))}>Complete</Button>
        </>
      }>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
          <Field label="Lot / QR"><TextInput value={lot} onChange={setLot} placeholder="LOT-123" /></Field>
          <Button variant="ghost" onClick={() => run('Đã gắn lot', () => api(apiBase, `/wip/jobs/${jobId}/scan`, { method: 'POST', body: JSON.stringify({ code: lot }) }), () => setLot(''))}>Scan lot</Button>
        </div>
      </Section>

      <Section title={`Station ${stationId}`} actions={<Field label="Station"><NumberInput value={stationId} onChange={setStationId} /></Field>}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
          <Field label="Số lượng"><NumberInput value={qty} onChange={setQty} /></Field>
          <Button onClick={() => run('Đã ghi count', () => api(apiBase, '/wip/counts', { method: 'POST', body: JSON.stringify({ station_id: stationId, qty }) }), () => total.reload())}>+ Count</Button>
        </div>
        <p style={{ fontSize: 13 }}>Tổng sản lượng: <b>{total.data?.total ?? 0}</b> · Trạng thái: <b>{String(stStatus.data?.status ?? '—')}</b></p>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {STATION_STATES.map((s) => (
            <Button key={s} variant="ghost" onClick={() => run(`Station → ${s}`, () => api(apiBase, `/wip/stations/${stationId}/status`, { method: 'PUT', body: JSON.stringify({ status: s }) }), () => stStatus.reload())}>{s}</Button>
          ))}
        </div>
      </Section>
    </>
  );
}
