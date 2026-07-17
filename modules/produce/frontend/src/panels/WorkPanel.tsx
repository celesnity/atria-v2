import { useState } from 'react';
import { ActionIcon, Tooltip } from '@mantine/core';
import { IconEye } from '@tabler/icons-react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';
import TaskDetailModal from './TaskDetailModal';
import { LineSelect, OperatorSelect } from '../ui/selects';

export default function WorkPanel({ apiBase, mode = 'board' }: { apiBase: string; mode?: 'queue' | 'board' | 'load' }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [operator, setOperator] = useState('op1');
  const [loadShiftId, setLoadShiftId] = useState(1);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);

  const shiftLoad = useApi<Array<Record<string, unknown>>>(apiBase, `/work/shift/${loadShiftId}/load`, [loadShiftId]);

  const board = useApi<Array<Record<string, unknown>>>(apiBase, `/work/board/${lineId}`, [lineId]);
  const queue = useApi<Array<Record<string, unknown>>>(apiBase, `/work/queue/${operator}`, [operator]);
  const active = mode === 'queue' ? queue : board;

  const addTask = async () => {
    try { await api(apiBase, '/work/tasks', { method: 'POST', body: JSON.stringify({ line_id: lineId }) }); board.reload(); notify('Đã tạo task'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const claim = async (id: number) => {
    try { await api(apiBase, `/work/tasks/${id}/claim`, { method: 'POST', body: JSON.stringify({ assignee_id: operator }) }); active.reload(); notify('Đã nhận task'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const assign = async (id: number) => {
    try { await api(apiBase, `/work/tasks/${id}/assign`, { method: 'POST', body: JSON.stringify({ assignee_id: operator }) }); active.reload(); notify('Đã gán task'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const statusKeys = ['queued', 'assigned', 'in_progress', 'done', 'blocked'];
  const detailCell = (r: Record<string, unknown>) => {
    const parts = statusKeys.filter((k) => r[k] !== undefined).map((k) => String(r[k]));
    return <span>{parts.join('/')}</span>;
  };

  if (mode === 'load') {
    return (
      <Section
        title={`Tải công việc toàn ca · ca ${loadShiftId}`}
        actions={<Field label="Shift"><NumberInput value={loadShiftId} onChange={setLoadShiftId} /></Field>}
      >
        <DataTable
          columns={[
            { key: 'line_id', label: 'Line' },
            { key: 'total', label: 'Tổng' },
            { key: 'detail', label: 'Chi tiết', render: detailCell },
          ]}
          rows={shiftLoad.data ?? []}
          empty="Chưa có dữ liệu tải"
        />
      </Section>
    );
  }

  return (
    <Section
      title={mode === 'queue' ? `Hàng đợi · ${operator}` : `Board tổ · line ${lineId}`}
      actions={mode === 'queue'
        ? <OperatorSelect value={operator} onChange={setOperator} />
        : <><LineSelect apiBase={apiBase} value={lineId} onChange={setLineId} /><OperatorSelect value={operator} onChange={setOperator} /><Button onClick={addTask}>+ Task</Button></>}
    >
      <DataTable
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'priority', label: 'Ưu tiên' },
          { key: 'assignee_id', label: 'Người làm' },
          { key: 'status', label: 'Trạng thái' },
          { key: 'act', label: '', render: (r) => (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'flex-end' }}>
              <Tooltip label="Xem chi tiết" withArrow>
                <ActionIcon variant="light" color="cobalt" radius="md" onClick={() => setDetail(r)} aria-label="Xem chi tiết">
                  <IconEye size={16} />
                </ActionIcon>
              </Tooltip>
              <Button variant="ghost" onClick={() => claim(r.id as number)}>Claim</Button>
              {mode === 'board' && <Button variant="ghost" onClick={() => assign(r.id as number)}>Assign</Button>}
            </div>
          ) },
        ]}
        rows={active.data ?? []}
        empty={mode === 'queue' ? 'Hàng đợi trống' : 'Chưa có task'}
      />
      <TaskDetailModal apiBase={apiBase} task={detail} onClose={() => setDetail(null)} />
    </Section>
  );
}
