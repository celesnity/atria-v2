import { useState } from 'react';
import { useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import { Field, NumberInput } from '../ui/Field';

export default function ReportPanel({ apiBase }: { apiBase: string }) {
  const [lineId, setLineId] = useState(1);
  const [shiftId, setShiftId] = useState(1);
  const [totalCount, setTotalCount] = useState(300);

  const live = useApi<{ tasks: unknown[]; open_andons: unknown[]; open_exceptions: unknown[] }>(apiBase, `/report/live/${lineId}`, [lineId]);
  const eos = useApi<Record<string, unknown>>(apiBase, `/report/end-of-shift?line_id=${lineId}&shift_id=${shiftId}&total_count=${totalCount}`, [lineId, shiftId, totalCount]);

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
    </>
  );
}
