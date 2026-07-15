import { useState } from 'react';
import { api, useApi } from '../api';
import Section from '../ui/Section';
import DataTable from '../ui/DataTable';
import Button from '../ui/Button';
import { Field, TextInput, NumberInput } from '../ui/Field';
import { useToast } from '../ui/Toast';

export default function ConfigPanel({ apiBase }: { apiBase: string }) {
  const { notify } = useToast();
  const [lineId, setLineId] = useState(1);
  const [lineCode, setLineCode] = useState('');
  const [lineName, setLineName] = useState('');
  const [partCode, setPartCode] = useState('');
  const [partName, setPartName] = useState('');
  const [ict, setIct] = useState(0);

  const lines = useApi<Array<Record<string, unknown>>>(apiBase, '/config/lines');
  const stations = useApi<Array<Record<string, unknown>>>(apiBase, `/config/lines/${lineId}/stations`, [lineId]);
  const parts = useApi<Array<Record<string, unknown>>>(apiBase, '/config/parts');

  const addLine = async () => {
    try {
      await api(apiBase, '/config/lines', { method: 'POST', body: JSON.stringify({ code: lineCode, name: lineName }) });
      setLineCode(''); setLineName(''); lines.reload(); notify('Đã tạo line');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const addPart = async () => {
    try {
      await api(apiBase, '/config/parts', { method: 'POST', body: JSON.stringify({ code: partCode, name: partName, ideal_cycle_time: ict || null }) });
      setPartCode(''); setPartName(''); setIct(0); parts.reload(); notify('Đã tạo phiên bản part');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };

  return (
    <>
      <Section title="Lines" actions={<Button onClick={addLine} disabled={!lineCode || !lineName}>+ Line</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Code"><TextInput value={lineCode} onChange={setLineCode} placeholder="L1" /></Field>
          <Field label="Name"><TextInput value={lineName} onChange={setLineName} placeholder="Line 1" /></Field>
        </div>
        <DataTable columns={[{ key: 'id', label: 'ID' }, { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }]} rows={lines.data ?? []} empty="Chưa có line" />
      </Section>

      <Section title={`Stations · line ${lineId}`} actions={<Field label="Line"><NumberInput value={lineId} onChange={setLineId} /></Field>}>
        <DataTable columns={[{ key: 'id', label: 'ID' }, { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }, { key: 'seq', label: 'Seq' }]} rows={stations.data ?? []} empty="Chưa có station" />
      </Section>

      <Section title="Parts (versioned)" actions={<Button onClick={addPart} disabled={!partCode || !partName}>+ Version</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Code"><TextInput value={partCode} onChange={setPartCode} placeholder="PN-1" /></Field>
          <Field label="Name"><TextInput value={partName} onChange={setPartName} /></Field>
          <Field label="Ideal cycle (s)"><NumberInput value={ict} onChange={setIct} /></Field>
        </div>
        <DataTable columns={[{ key: 'code', label: 'Code' }, { key: 'version', label: 'Ver' }, { key: 'name', label: 'Name' }, { key: 'ideal_cycle_time', label: 'ICT (s)' }]} rows={parts.data ?? []} empty="Chưa có part" />
      </Section>
    </>
  );
}
