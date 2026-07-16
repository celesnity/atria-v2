import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, TextInput, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';
import { SopSelect } from '../ui/selects';

export default function SopPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [sopId, setSopId] = useState(1);
  const [versionId, setVersionId] = useState(1);
  const [jobId, setJobId] = useState(1);
  const [stepIndex, setStepIndex] = useState(0);
  const [value, setValue] = useState(0);
  const [diff, setDiff] = useState<{ current_version: number; previous_version: number; added: string[]; removed: string[]; changed: string[] } | null>(null);

  const released = useApi<Record<string, unknown> | null>(apiBase, `/sop/sops/${sopId}/released`, [sopId]);
  const progress = useApi<Array<Record<string, unknown>>>(apiBase, `/sop/jobs/${jobId}/progress`, [jobId]);

  const publish = async () => {
    try { await api(apiBase, `/sop/versions/${versionId}/publish`, { method: 'POST' }); released.reload(); notify('Đã phát hành bản duyệt'); }
    catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const confirm = async () => {
    try {
      await api(apiBase, '/sop/step-confirms', { method: 'POST', body: JSON.stringify({ job_id: jobId, sop_version_id: versionId, step_index: stepIndex, value: value || null }) });
      progress.reload(); notify(`Đã xác nhận bước ${stepIndex}`);
    } catch (e) { notify(String((e as Error).message), 'err'); }  // poka-yoke 409 lands here
  };

  const compareDiff = async () => {
    try {
      const d = await api<{ current_version: number; previous_version: number; added: string[]; removed: string[]; changed: string[] }>(apiBase, `/sop/sops/${sopId}/diff`);
      setDiff(d);
    } catch (e) {
      notify(String((e as Error).message), 'err');
    }
  };

  const steps = (released.data?.steps as Array<Record<string, unknown>>) ?? [];

  return (
    <>
      <Section title="SOP đã phát hành" actions={<><SopSelect apiBase={apiBase} value={sopId} onChange={setSopId} /><Field label="Version id"><NumberInput value={versionId} onChange={setVersionId} /></Field><Button onClick={publish}>Publish</Button></>}>
        <DataTable columns={[{ key: 'name', label: 'Step' }, { key: 'required', label: 'Bắt buộc', render: (r) => (r.required ? '✓' : '') }, { key: 'min', label: 'Min' }, { key: 'max', label: 'Max' }]} rows={steps} empty="Chưa có bản approved" />
      </Section>

      <Section title="Xác nhận bước (poka-yoke)" actions={<Button onClick={confirm}>Confirm step</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Job id"><NumberInput value={jobId} onChange={setJobId} /></Field>
          <Field label="Step index"><NumberInput value={stepIndex} onChange={setStepIndex} /></Field>
          <Field label="Giá trị đo"><NumberInput value={value} onChange={setValue} /></Field>
        </div>
        <DataTable columns={[{ key: 'step_index', label: 'Bước' }, { key: 'value', label: 'Giá trị' }, { key: 'confirmed_at', label: 'Lúc' }]} rows={progress.data ?? []} empty="Chưa xác nhận bước nào" />
      </Section>

      <Section title="Thay đổi so với bản trước" actions={<><SopSelect apiBase={apiBase} value={sopId} onChange={setSopId} /><Button onClick={compareDiff}>So sánh</Button></>}>
        {diff ? (
          <div style={{ fontSize: 13 }}>
            <p>Bản hiện tại: <b>{diff.current_version}</b> · Bản trước: <b>{diff.previous_version}</b></p>
            <DataTable columns={[{ key: 'v', label: 'Thêm mới' }]} rows={diff.added.map((v) => ({ v }))} empty="Không có" />
            <DataTable columns={[{ key: 'v', label: 'Đã xóa' }]} rows={diff.removed.map((v) => ({ v }))} empty="Không có" />
            <DataTable columns={[{ key: 'v', label: 'Thay đổi' }]} rows={diff.changed.map((v) => ({ v }))} empty="Không có" />
          </div>
        ) : (
          <p style={{ fontSize: 13, color: '#888' }}>Nhấn So sánh để xem thay đổi (P-EXEC-05).</p>
        )}
      </Section>
    </>
  );
}
