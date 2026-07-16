import { useState } from 'react';
import { ActionIcon, Tooltip } from '@mantine/core';
import { IconEye, IconAlertTriangle } from '@tabler/icons-react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';
import DetailModal from '../ui/DetailModal';
import RowDetail from '../ui/RowDetail';
import { LineSelect, StationSelect, CategorySelect } from '../ui/selects';

const DT_LABELS: Record<string, string> = {
  id: 'Mã sự cố', station_id: 'Trạm', shift_id: 'Ca', category: 'Nhóm',
  subcategory: 'Nhóm phụ', code: 'Mã lý do', started_at: 'Bắt đầu', ended_at: 'Kết thúc',
  elapsed_minutes: 'Đã trôi (phút)',
};

export default function DowntimePanel({ apiBase, mode = 'log' }: { apiBase: string; mode?: 'log' | 'andon' }) {
  const { notify } = useToast();
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [lineId, setLineId] = useState(1);
  const [stationId, setStationId] = useState(1);
  const [category, setCategory] = useState('Mechanical');
  const [threshold, setThreshold] = useState(15);
  const [reasonCategory, setReasonCategory] = useState('');
  const [reasonSubcategory, setReasonSubcategory] = useState('');
  const [reasonCode, setReasonCode] = useState('');
  const [reasonMachine, setReasonMachine] = useState('');

  const open = useApi<Array<Record<string, unknown>>>(apiBase, '/downtime/events/open');
  const andons = useApi<Array<Record<string, unknown>>>(apiBase, `/downtime/andon/line/${lineId}`, [lineId]);
  const alerts = useApi<Array<Record<string, unknown>>>(apiBase, `/downtime/alerts?threshold_minutes=${threshold}`, [threshold]);
  const reasons = useApi<Array<Record<string, unknown>>>(apiBase, `/downtime/lines/${lineId}/reasons`, [lineId]);

  const run = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    try { await fn(); after?.(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  if (mode === 'andon') {
    return (
      <>
        <Section title={`Andon · line ${lineId}`} actions={<LineSelect apiBase={apiBase} value={lineId} onChange={setLineId} />}>
          <DataTable
            columns={[
              { key: 'id', label: 'ID' }, { key: 'station_id', label: 'Station' }, { key: 'reason', label: 'Lý do' }, { key: 'status', label: 'Trạng thái' },
              { key: 'act', label: '', render: (r) => (
                <div style={{ display: 'flex', gap: 6 }}>
                  <Button variant="ghost" onClick={() => run('Acknowledged', () => api(apiBase, `/downtime/andon/${r.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'acknowledged' }) }), () => andons.reload())}>Ack</Button>
                  <Button variant="ghost" onClick={() => run('Resolved', () => api(apiBase, `/downtime/andon/${r.id}/status`, { method: 'POST', body: JSON.stringify({ status: 'resolved' }) }), () => andons.reload())}>Resolve</Button>
                </div>
              ) },
            ]}
            rows={andons.data ?? []}
            empty="Không có andon đang mở"
          />
        </Section>
        <Section title="Cảnh báo downtime quá lâu" actions={<Field label="Ngưỡng (phút)"><NumberInput value={threshold} onChange={setThreshold} /></Field>}>
          <DataTable
            columns={[
              { key: 'id', label: 'ID' }, { key: 'station_id', label: 'Station' }, { key: 'category', label: 'Category' }, { key: 'elapsed_minutes', label: 'Đã trôi (phút)' },
            ]}
            rows={alerts.data ?? []}
            empty="Không có cảnh báo"
          />
        </Section>
      </>
    );
  }

  return (
    <>
      <Section title="Ghi downtime" actions={
        <>
          <StationSelect apiBase={apiBase} value={stationId} onChange={setStationId} />
          <CategorySelect value={category} onChange={setCategory} />
          <Button onClick={() => run('Đã ghi downtime', () => api(apiBase, '/downtime/events', { method: 'POST', body: JSON.stringify({ station_id: stationId, category }) }), () => open.reload())}>Log</Button>
        </>
      }>
        <DataTable
          columns={[
            { key: 'id', label: 'ID' }, { key: 'station_id', label: 'Station' }, { key: 'category', label: 'Category' }, { key: 'started_at', label: 'Bắt đầu' },
            { key: 'act', label: '', render: (r) => (
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'flex-end' }}>
                <Tooltip label="Xem chi tiết" withArrow>
                  <ActionIcon variant="light" color="cobalt" radius="md" onClick={() => setDetail(r)} aria-label="Xem chi tiết"><IconEye size={16} /></ActionIcon>
                </Tooltip>
                <Button variant="ghost" onClick={() => run('Đã đóng', () => api(apiBase, `/downtime/events/${r.id}/close`, { method: 'POST' }), () => open.reload())}>Close</Button>
              </div>
            ) },
          ]}
          rows={open.data ?? []}
          empty="Không có downtime mở"
        />
      </Section>
      <Section title="Andon" actions={<><LineSelect apiBase={apiBase} value={lineId} onChange={setLineId} /><Button variant="danger" onClick={() => run('Đã gọi andon', () => api(apiBase, '/downtime/andon', { method: 'POST', body: JSON.stringify({ line_id: lineId, station_id: stationId }) }))}>Gọi andon</Button></>}>
        <p style={{ fontSize: 13, color: '#888' }}>Gọi hỗ trợ khi không tự xử được (P-DOWN-02).</p>
      </Section>
      <Section title="Thư viện mã lý do" actions={
        <>
          <LineSelect apiBase={apiBase} value={lineId} onChange={setLineId} />
          <CategorySelect value={reasonCategory} onChange={setReasonCategory} label="Category" />
          <Field label="Subcategory"><TextInput value={reasonSubcategory} onChange={setReasonSubcategory} /></Field>
          <Field label="Code"><TextInput value={reasonCode} onChange={setReasonCode} /></Field>
          <Field label="Machine"><TextInput value={reasonMachine} onChange={setReasonMachine} /></Field>
          <Button onClick={() => run('Đã thêm lý do', () => api(apiBase, `/downtime/lines/${lineId}/reasons`, { method: 'POST', body: JSON.stringify({ category: reasonCategory, subcategory: reasonSubcategory, code: reasonCode, machine: reasonMachine }) }), () => reasons.reload())}>+ Lý do</Button>
        </>
      }>
        <DataTable
          columns={[
            { key: 'id', label: 'ID' }, { key: 'machine', label: 'Máy' }, { key: 'category', label: 'Category' }, { key: 'subcategory', label: 'Subcategory' }, { key: 'code', label: 'Code' },
          ]}
          rows={reasons.data ?? []}
          empty="Chưa có mã lý do"
        />
      </Section>

      <DetailModal
        opened={!!detail}
        onClose={() => setDetail(null)}
        title={detail ? `Sự cố downtime #${detail.id}` : 'Downtime'}
        subtitle="Chi tiết sự kiện dừng máy"
        icon={<IconAlertTriangle size={20} />}
      >
        {detail ? <RowDetail row={detail} labels={DT_LABELS} /> : null}
      </DetailModal>
    </>
  );
}
