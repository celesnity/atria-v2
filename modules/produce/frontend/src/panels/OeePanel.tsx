import { useState } from 'react';
import { useMinderTheme } from 'minder-ui-sdk';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import Button from '../ui/Button';
import { Field, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function OeePanel({ apiBase }: { apiBase: string }) {
  const { tokens } = useMinderTheme();
  const { notify } = useToast();
  const [shiftId, setShiftId] = useState(1);
  const [lineId, setLineId] = useState(1);
  const [ict, setIct] = useState(60);
  const [target, setTarget] = useState(500);
  const [planned, setPlanned] = useState(480);
  const [totalCount, setTotalCount] = useState(400);

  const oee = useApi<Record<string, number> & { error?: string }>(apiBase, `/oee/shifts/${shiftId}?total_count=${totalCount}`, [shiftId, totalCount]);

  const load = async () => {
    try {
      await api(apiBase, '/oee/production-orders', { method: 'POST', body: JSON.stringify({ line_id: lineId, shift_id: shiftId, ideal_cycle_time: ict, target_count: target, planned_minutes: planned }) });
      oee.reload(); notify('Đã nạp production order');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  const gauge = (label: string, v: number | undefined) => (
    <div style={{ flex: 1, background: tokens.surfaceAlt, borderRadius: 10, padding: 14, textAlign: 'center' }}>
      <div style={{ fontSize: 12, color: tokens.textMuted }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: tokens.text }}>{v === undefined ? '—' : `${Math.round(v * 100)}%`}</div>
    </div>
  );

  return (
    <>
      <Section title="Nạp production order (chuẩn ca)" actions={<Button onClick={load}>Nạp</Button>}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>
          <Field label="Shift"><NumberInput value={shiftId} onChange={setShiftId} /></Field>
          <Field label="Ideal cycle (s)"><NumberInput value={ict} onChange={setIct} /></Field>
          <Field label="Target"><NumberInput value={target} onChange={setTarget} /></Field>
          <Field label="Planned (phút)"><NumberInput value={planned} onChange={setPlanned} /></Field>
        </div>
      </Section>

      <Section title={`OEE ca ${shiftId}`} actions={<Field label="Sản lượng ca"><NumberInput value={totalCount} onChange={setTotalCount} /></Field>}>
        {oee.data?.error ? (
          <p style={{ color: tokens.warning, fontSize: 13 }}>{oee.data.error}</p>
        ) : (
          <div style={{ display: 'flex', gap: 10 }}>
            {gauge('Availability', oee.data?.availability)}
            {gauge('Performance', oee.data?.performance)}
            {gauge('Quality', oee.data?.quality)}
            {gauge('OEE', oee.data?.oee)}
          </div>
        )}
      </Section>
    </>
  );
}
