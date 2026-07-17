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
  const [skillCode, setSkillCode] = useState('');
  const [skillName, setSkillName] = useState('');
  const [operatorId, setOperatorId] = useState('op1');
  const [grantSkillId, setGrantSkillId] = useState(0);
  const [opCode, setOpCode] = useState('');
  const [opName, setOpName] = useState('');
  const [opStationId, setOpStationId] = useState(0);
  const [opSkillId, setOpSkillId] = useState(0);

  const lines = useApi<Array<Record<string, unknown>>>(apiBase, '/config/lines');
  const stations = useApi<Array<Record<string, unknown>>>(apiBase, `/config/lines/${lineId}/stations`, [lineId]);
  const operations = useApi<Array<Record<string, unknown>>>(apiBase, `/config/lines/${lineId}/operations`, [lineId]);
  const parts = useApi<Array<Record<string, unknown>>>(apiBase, '/config/parts');
  const skills = useApi<Array<Record<string, unknown>>>(apiBase, '/config/skills');
  const operatorSkills = useApi<Array<number>>(apiBase, `/config/operators/${operatorId}/skills`, [operatorId]);

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
  const addSkill = async () => {
    try {
      await api(apiBase, '/config/skills', { method: 'POST', body: JSON.stringify({ code: skillCode, name: skillName }) });
      setSkillCode(''); setSkillName(''); skills.reload(); notify('Đã tạo kỹ năng');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const addOperation = async () => {
    try {
      await api(apiBase, `/config/lines/${lineId}/operations`, { method: 'POST', body: JSON.stringify({ code: opCode, name: opName, station_id: opStationId || null, required_skill_id: opSkillId || null }) });
      setOpCode(''); setOpName(''); setOpStationId(0); setOpSkillId(0); operations.reload(); notify('Đã tạo operation');
    } catch (e) { notify(String((e as Error).message), 'err'); }
  };
  const grantSkill = async () => {
    try {
      await api(apiBase, `/config/operators/${operatorId}/skills`, { method: 'POST', body: JSON.stringify({ skill_id: grantSkillId }) });
      setGrantSkillId(0); operatorSkills.reload(); notify('Đã cấp kỹ năng');
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

      <Section title={`Operations · line ${lineId}`} actions={<Button onClick={addOperation} disabled={!opCode || !opName}>+ Operation</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
          <Field label="Code"><TextInput value={opCode} onChange={setOpCode} placeholder="OP-10" /></Field>
          <Field label="Name"><TextInput value={opName} onChange={setOpName} /></Field>
          <Field label="Station id"><NumberInput value={opStationId} onChange={setOpStationId} /></Field>
          <Field label="Required skill id"><NumberInput value={opSkillId} onChange={setOpSkillId} /></Field>
        </div>
        <DataTable columns={[{ key: 'id', label: 'ID' }, { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }, { key: 'station_id', label: 'Station' }, { key: 'required_skill_id', label: 'Skill' }]} rows={operations.data ?? []} empty="Chưa có operation" />
      </Section>

      <Section title="Parts (versioned)" actions={<Button onClick={addPart} disabled={!partCode || !partName}>+ Version</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Code"><TextInput value={partCode} onChange={setPartCode} placeholder="PN-1" /></Field>
          <Field label="Name"><TextInput value={partName} onChange={setPartName} /></Field>
          <Field label="Ideal cycle (s)"><NumberInput value={ict} onChange={setIct} /></Field>
        </div>
        <DataTable columns={[{ key: 'code', label: 'Code' }, { key: 'version', label: 'Ver' }, { key: 'name', label: 'Name' }, { key: 'ideal_cycle_time', label: 'ICT (s)' }]} rows={parts.data ?? []} empty="Chưa có part" />
      </Section>

      <Section title="Skills" actions={<Button onClick={addSkill} disabled={!skillCode || !skillName}>+ Skill</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Code"><TextInput value={skillCode} onChange={setSkillCode} placeholder="SK-1" /></Field>
          <Field label="Name"><TextInput value={skillName} onChange={setSkillName} placeholder="Hàn" /></Field>
        </div>
        <DataTable columns={[{ key: 'id', label: 'ID' }, { key: 'code', label: 'Code' }, { key: 'name', label: 'Name' }]} rows={skills.data ?? []} empty="Chưa có kỹ năng" />
      </Section>

      <Section title={`Operator skills · ${operatorId}`} actions={<Button onClick={grantSkill} disabled={!operatorId || !grantSkillId}>Cấp kỹ năng</Button>}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Field label="Operator"><TextInput value={operatorId} onChange={setOperatorId} placeholder="op1" /></Field>
          <Field label="Skill id"><NumberInput value={grantSkillId} onChange={setGrantSkillId} /></Field>
        </div>
        <DataTable columns={[{ key: 'skill_id', label: 'Skill id' }]} rows={(operatorSkills.data ?? []).map((id) => ({ skill_id: id }))} empty="Chưa cấp kỹ năng" />
      </Section>
    </>
  );
}
