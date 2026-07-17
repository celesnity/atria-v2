import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, NumberInput, TextInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function ScrapPanel({ apiBase, mode = 'record' }: { apiBase: string; mode?: 'record' | 'hold' }) {
  const { notify } = useToast();
  const [shiftId, setShiftId] = useState(1);
  const [reason, setReason] = useState('D-01');
  const [qty, setQty] = useState(1);
  const [lot, setLot] = useState('');

  const [scrapId, setScrapId] = useState(1);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);

  const total = useApi<{ total: number }>(apiBase, `/scrap/total?shift_id=${shiftId}`, [shiftId]);
  const holds = useApi<Array<Record<string, unknown>>>(apiBase, '/scrap/holds/active');
  const byStation = useApi<Array<{ station_id: number; scrap: number }>>(apiBase, `/scrap/by-station?shift_id=${shiftId}`, [shiftId]);

  const uploadPhoto = async (file: File) => {
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`${apiBase}/scrap/records/${scrapId}/photo`, { method: 'POST', body: fd });
      if (!res.ok) {
        const { detail } = await res.json();
        notify(detail, 'err');
        return;
      }
      const { url } = await res.json();
      setPhotoUrl(url);
      notify('Đã tải ảnh');
    } catch (e) {
      notify(String((e as Error).message), 'err');
    }
  };

  const run = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    try { await fn(); after?.(); notify(label); } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  if (mode === 'hold') {
    return (
      <Section title="Lot đang hold" actions={<><Field label="Lot"><TextInput value={lot} onChange={setLot} /></Field><Button variant="danger" onClick={() => run('Đã hold lot', () => api(apiBase, '/scrap/holds', { method: 'POST', body: JSON.stringify({ lot_code: lot }) }), () => { setLot(''); holds.reload(); })}>Hold</Button></>}>
        <DataTable
          columns={[
            { key: 'id', label: 'ID' }, { key: 'lot_code', label: 'Lot' }, { key: 'reason', label: 'Lý do' }, { key: 'held_at', label: 'Lúc' },
            { key: 'act', label: '', render: (r) => <Button variant="ghost" onClick={() => run('Đã release', () => api(apiBase, `/scrap/holds/${r.id}/release`, { method: 'POST' }), () => holds.reload())}>Release</Button> },
          ]}
          rows={holds.data ?? []}
          empty="Không có lot hold"
        />
      </Section>
    );
  }

  return (
    <>
      <Section title="Ghi phế phẩm" actions={
        <>
          <Field label="Shift"><NumberInput value={shiftId} onChange={setShiftId} /></Field>
          <Field label="Mã lỗi"><TextInput value={reason} onChange={setReason} /></Field>
          <Field label="SL"><NumberInput value={qty} onChange={setQty} /></Field>
          <Button onClick={() => run('Đã ghi phế phẩm', () => api(apiBase, '/scrap/records', { method: 'POST', body: JSON.stringify({ reason_code: reason, qty, shift_id: shiftId }) }), () => total.reload())}>Ghi</Button>
        </>
      }>
        <p style={{ fontSize: 13 }}>Tổng phế phẩm ca {shiftId}: <b>{total.data?.total ?? 0}</b></p>
      </Section>
      <Section title="Rework" actions={<><Field label="Lot"><TextInput value={lot} onChange={setLot} /></Field><Button variant="ghost" onClick={() => run('Đã đánh dấu rework', () => api(apiBase, '/scrap/rework', { method: 'POST', body: JSON.stringify({ lot_code: lot }) }), () => setLot(''))}>Đánh dấu rework</Button></>}>
        <p style={{ fontSize: 13, color: '#888' }}>Đưa lot vào luồng rework (P-SCRAP-02).</p>
      </Section>
      <Section title="Phế phẩm theo station">
        <DataTable
          columns={[{ key: 'station_id', label: 'Station' }, { key: 'scrap', label: 'Phế phẩm' }]}
          rows={byStation.data ?? []}
          empty="Chưa có dữ liệu"
        />
      </Section>
      <Section title="Ảnh lỗi" actions={
        <>
          <Field label="Scrap record id"><NumberInput value={scrapId} onChange={setScrapId} /></Field>
          <input type="file" accept="image/*" onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadPhoto(f); }} />
        </>
      }>
        {photoUrl
          ? <a href={photoUrl} target="_blank" rel="noreferrer"><img src={photoUrl} style={{ maxWidth: 200 }} alt="Ảnh lỗi" /></a>
          : <p style={{ fontSize: 13, color: '#888' }}>Chọn ảnh để tải lên (P-SCRAP-03).</p>}
      </Section>
    </>
  );
}
