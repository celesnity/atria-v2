import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function ReportPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [shiftId, setShiftId] = useState(1);
  const [totalCount, setTotalCount] = useState(300);
  const [entryShift, setEntryShift] = useState(1);
  const [entryCount, setEntryCount] = useState(300);
  const [entries, setEntries] = useState<Array<{ shift_id: number; total_count: number }>>([]);
  const [trend, setTrend] = useState<Array<Record<string, unknown>>>([]);

  const live = useApi<{ tasks: unknown[]; open_andons: unknown[]; open_exceptions: unknown[] }>(apiBase, `/report/live/${lineId}`, [lineId]);
  const eos = useApi<Record<string, unknown>>(apiBase, `/report/end-of-shift?line_id=${lineId}&shift_id=${shiftId}&total_count=${totalCount}`, [lineId, shiftId, totalCount]);
  const whyLate = useApi<Record<string, unknown>>(apiBase, `/report/why-late/${lineId}?shift_id=${shiftId}`, [lineId, shiftId]);

  const addEntry = () => setEntries((prev) => [...prev, { shift_id: entryShift, total_count: entryCount }]);
  const computeTrend = async () => {
    try {
      const res = await api<Array<Record<string, unknown>>>(apiBase, '/report/trend', { method: 'POST', body: JSON.stringify({ entries }) });
      setTrend(res);
      notify('Đã tính xu hướng OEE');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  return (
    <>
      <Section title="Dashboard live" actions={<Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>}>
        <div style={{ display: 'flex', gap: 24, fontSize: 13 }}>
          <div>Task: <b>{live.data?.tasks.length ?? 0}</b></div>
          <div>Andon mở: <b>{live.data?.open_andons.length ?? 0}</b></div>
          <div>Ngoại lệ mở: <b>{live.data?.open_exceptions.length ?? 0}</b></div>
        </div>
      </Section>

      <Section title="Báo cáo cuối ca" actions={<><Field label="Shift"><NumberInput value={shiftId} onChange={setShiftId} /></Field><Field label="Sản lượng"><NumberInput value={totalCount} onChange={setTotalCount} /></Field></>}>
        <div style={{ fontSize: 13, marginBottom: 12 }}>
          Sản lượng: <b>{String(eos.data?.output_count ?? 0)}</b> · Phế phẩm: <b>{String(eos.data?.scrap_count ?? 0)}</b> ·
          OEE: <b>{(eos.data?.oee as Record<string, unknown>)?.oee !== undefined ? String((eos.data?.oee as Record<string, unknown>).oee) : '—'}</b>
        </div>
        <DataTable columns={[{ key: 'category', label: 'Lý do downtime' }, { key: 'count', label: 'Số lần' }]} rows={(eos.data?.top_downtime_reasons as Array<Record<string, unknown>>) ?? []} empty="Không có downtime" />
      </Section>

      <Section title="Vì sao line trễ?">
        <div style={{ fontSize: 13, marginBottom: 12 }}>
          Downtime dài: <b>{((whyLate.data?.long_downtimes as unknown[]) ?? []).length}</b> ·
          Ngoại lệ mở: <b>{((whyLate.data?.open_exceptions as unknown[]) ?? []).length}</b>
        </div>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <DataTable columns={[{ key: 'category', label: 'Lý do downtime' }, { key: 'count', label: 'Số lần' }]} rows={(whyLate.data?.top_downtime_reasons as Array<Record<string, unknown>>) ?? []} empty="Không có downtime" />
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <DataTable columns={[{ key: 'station_id', label: 'Trạm' }, { key: 'scrap', label: 'Phế phẩm' }]} rows={(whyLate.data?.scrap_by_station as Array<Record<string, unknown>>) ?? []} empty="Không có phế phẩm" />
          </div>
        </div>
      </Section>

      <Section title="Xu hướng OEE" actions={
        <>
          <Field label="Shift"><NumberInput value={entryShift} onChange={setEntryShift} /></Field>
          <Field label="Sản lượng"><NumberInput value={entryCount} onChange={setEntryCount} /></Field>
          <Button onClick={addEntry}>+ thêm ca</Button>
          <Button onClick={computeTrend}>Tính</Button>
        </>
      }>
        <div style={{ fontSize: 13, marginBottom: 12 }}>
          Ca đã thêm: {entries.length ? entries.map((en) => `#${en.shift_id} (${en.total_count})`).join(', ') : '—'}
        </div>
        <DataTable columns={[{ key: 'shift_id', label: 'Shift' }, { key: 'oee', label: 'OEE' }]} rows={trend} empty="Chưa tính xu hướng" />
      </Section>
    </>
  );
}
