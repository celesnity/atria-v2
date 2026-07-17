import { useState } from 'react';
import { Button as MButton } from '@mantine/core';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';
import { statusColorMantine } from '../theme.mantine';
import { StationSelect } from '../ui/selects';

const STATION_STATES = ['idle', 'running', 'down', 'blocked', 'setup'];

export default function WipPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [taskId, setTaskId] = useState(1);
  const [jobId, setJobId] = useState(1);
  const [stationId, setStationId] = useState(1);
  const [qty, setQty] = useState(1);
  const [lot, setLot] = useState('');
  const [lotCode, setLotCode] = useState('');

  const total = useApi<{ total: number }>(apiBase, `/wip/stations/${stationId}/total`, [stationId]);
  const stStatus = useApi<Record<string, unknown> | null>(apiBase, `/wip/stations/${stationId}/status`, [stationId]);
  const wip = useApi<Array<Record<string, unknown>>>(apiBase, '/wip/wip');
  const [progress, setProgress] = useState<{ code: string; jobs: Array<Record<string, unknown>>; job_count: number; done_count: number } | null>(null);

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

      <Section title={`Station ${stationId}`} actions={<StationSelect apiBase={apiBase} value={stationId} onChange={setStationId} />}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
          <Field label="Số lượng"><NumberInput value={qty} onChange={setQty} /></Field>
          <Button onClick={() => run('Đã ghi count', () => api(apiBase, '/wip/counts', { method: 'POST', body: JSON.stringify({ station_id: stationId, qty }) }), () => total.reload())}>+ Count</Button>
        </div>
        <p style={{ fontSize: 13 }}>Tổng sản lượng: <b>{total.data?.total ?? 0}</b> · Trạng thái: <b>{String(stStatus.data?.status ?? '—')}</b></p>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {STATION_STATES.map((s) => {
            const active = String(stStatus.data?.status ?? '') === s;
            return (
              <MButton
                key={s}
                size="xs"
                radius="xl"
                color={statusColorMantine(s)}
                variant={active ? 'filled' : 'light'}
                onClick={() => run(`Station → ${s}`, () => api(apiBase, `/wip/stations/${stationId}/status`, { method: 'PUT', body: JSON.stringify({ status: s }) }), () => stStatus.reload())}
                styles={{ root: { fontWeight: 600, textTransform: 'capitalize' } }}
              >
                {s}
              </MButton>
            );
          })}
        </div>
      </Section>

      <Section title="WIP theo station" actions={<Button variant="ghost" onClick={() => wip.reload()}>Tải lại</Button>}>
        <DataTable
          columns={[
            { key: 'station_id', label: 'Station' }, { key: 'wip', label: 'WIP' },
          ]}
          rows={wip.data ?? []}
          empty="Không có WIP"
        />
      </Section>

      <Section title="Tiến độ lot" actions={
        <>
          <Field label="Lot"><TextInput value={lotCode} onChange={setLotCode} placeholder="LOT-123" /></Field>
          <Button onClick={() => run('Đã tra tiến độ', async () => { const p = await api<{ code: string; jobs: Array<Record<string, unknown>>; job_count: number; done_count: number }>(apiBase, `/wip/lots/${lotCode}/progress`); setProgress(p); })}>Tra</Button>
        </>
      }>
        <p style={{ fontSize: 13 }}>Số job: <b>{progress?.job_count ?? 0}</b> · Hoàn thành: <b>{progress?.done_count ?? 0}</b></p>
        <DataTable
          columns={[
            { key: 'id', label: 'ID' }, { key: 'status', label: 'Trạng thái' }, { key: 'steps_recorded', label: 'Số bước' },
          ]}
          rows={progress?.jobs ?? []}
          empty="Chưa tra lot"
        />
      </Section>
    </>
  );
}
