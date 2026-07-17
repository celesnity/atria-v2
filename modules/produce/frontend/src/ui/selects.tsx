import { Select, Autocomplete } from '@mantine/core';
import { useQueries } from '@tanstack/react-query';
import { useMinderPopupTarget } from 'minder-ui-sdk';
import { api } from '../api';
import { useApiQuery } from '../hooks/useApiQuery';

type Row = Record<string, unknown>;

// Dropdowns are popups: portal them into the SDK's host-level popup layer so
// they escape the host's clipped module container and keep the scoped Mantine
// CSS variables. Fall back to the in-page scoped root (never the plain body,
// which lacks the scoped vars and would render the menu unstyled/invisible).
function useCombobox() {
  const scoped =
    typeof document !== 'undefined'
      ? (document.querySelector('[data-produce-dashboard]') as HTMLElement | null)
      : null;
  const target = useMinderPopupTarget() ?? scoped;
  return { withinPortal: true, portalProps: target ? { target } : undefined };
}

/** Line picker — options from /config/lines. */
export function LineSelect({ apiBase, value, onChange, label = 'Line', w = 190 }: {
  apiBase: string; value: number; onChange: (v: number) => void; label?: string; w?: number;
}) {
  const q = useApiQuery<Row[]>(apiBase, '/config/lines');
  const combobox = useCombobox();
  const data = (q.data ?? []).map((l) => ({ value: String(l.id), label: `${l.code} · ${l.name}` }));
  return (
    <Select
      label={label} data={data} value={value ? String(value) : null}
      onChange={(v) => onChange(Number(v) || 0)} w={w} size="sm" searchable
      checkIconPosition="right" allowDeselect={false} nothingFoundMessage="Không có line"
      placeholder="Chọn line" comboboxProps={combobox}
    />
  );
}

/** Station picker — all stations across lines (or one line if `lineId` given). */
export function StationSelect({ apiBase, value, onChange, lineId, label = 'Trạm', w = 200 }: {
  apiBase: string; value: number; onChange: (v: number) => void; lineId?: number; label?: string; w?: number;
}) {
  const lines = useApiQuery<Row[]>(apiBase, '/config/lines');
  const lineIds = lineId ? [lineId] : (lines.data ?? []).map((l) => Number(l.id));
  const stationQs = useQueries({
    queries: lineIds.map((id) => ({
      queryKey: ['produce', apiBase, `/config/lines/${id}/stations`],
      queryFn: () => api<Row[]>(apiBase, `/config/lines/${id}/stations`),
      enabled: !!id,
      staleTime: 60_000,
    })),
  });
  const stations = stationQs.flatMap((s) => s.data ?? []);
  const combobox = useCombobox();
  const data = stations.map((s) => ({ value: String(s.id), label: `${s.code} · ${s.name}` }));
  return (
    <Select
      label={label} data={data} value={value ? String(value) : null}
      onChange={(v) => onChange(Number(v) || 0)} w={w} size="sm" searchable
      checkIconPosition="right" allowDeselect={false} nothingFoundMessage="Không có trạm"
      placeholder="Chọn trạm" comboboxProps={combobox}
    />
  );
}

/** Part picker — options from /config/parts. */
export function PartSelect({ apiBase, value, onChange, label = 'Linh kiện', w = 210 }: {
  apiBase: string; value: number | null; onChange: (v: number) => void; label?: string; w?: number;
}) {
  const q = useApiQuery<Row[]>(apiBase, '/config/parts');
  const combobox = useCombobox();
  const data = (q.data ?? []).map((p) => ({ value: String(p.id), label: `${p.code} · ${p.name}` }));
  return (
    <Select
      label={label} data={data} value={value ? String(value) : null}
      onChange={(v) => onChange(Number(v) || 0)} w={w} size="sm" searchable clearable
      checkIconPosition="right" nothingFoundMessage="Không có" placeholder="Chọn linh kiện"
      comboboxProps={combobox}
    />
  );
}

/** SOP picker — options from /sop/sops. */
export function SopSelect({ apiBase, value, onChange, label = 'SOP', w = 220 }: {
  apiBase: string; value: number; onChange: (v: number) => void; label?: string; w?: number;
}) {
  const q = useApiQuery<Row[]>(apiBase, '/sop/sops');
  const combobox = useCombobox();
  const data = (q.data ?? []).map((sop) => ({ value: String(sop.id), label: `${sop.code} · ${sop.title}` }));
  return (
    <Select
      label={label} data={data} value={value ? String(value) : null}
      onChange={(v) => onChange(Number(v) || 0)} w={w} size="sm" searchable
      checkIconPosition="right" allowDeselect={false} nothingFoundMessage="Không có SOP"
      placeholder="Chọn SOP" comboboxProps={combobox}
    />
  );
}

/** Shift picker — options from /work/shifts. */
export function ShiftSelect({ apiBase, value, onChange, lineId, label = 'Ca', w = 170 }: {
  apiBase: string; value: number; onChange: (v: number) => void; lineId?: number; label?: string; w?: number;
}) {
  const q = useApiQuery<Row[]>(apiBase, lineId ? `/work/shifts?line_id=${lineId}` : '/work/shifts', { enabled: true });
  const combobox = useCombobox();
  const data = (q.data ?? []).map((sh) => ({ value: String(sh.id), label: `${sh.name} · line ${sh.line_id}` }));
  return (
    <Select
      label={label} data={data} value={value ? String(value) : null}
      onChange={(v) => onChange(Number(v) || 0)} w={w} size="sm" searchable
      checkIconPosition="right" allowDeselect={false} nothingFoundMessage="Không có ca"
      placeholder="Chọn ca" comboboxProps={combobox}
    />
  );
}

const DOWNTIME_CATEGORIES = ['Mechanical', 'Electrical', 'Quality', 'Material', 'Tooling', 'Setup'];

/** Downtime category picker — fixed enum used across the module. */
export function CategorySelect({ value, onChange, label = 'Category', w = 180 }: {
  value: string; onChange: (v: string) => void; label?: string; w?: number;
}) {
  const combobox = useCombobox();
  return (
    <Select
      label={label} data={DOWNTIME_CATEGORIES} value={value || null}
      onChange={(v) => onChange(v ?? '')} w={w} size="sm" allowDeselect={false}
      checkIconPosition="right" placeholder="Chọn nhóm" comboboxProps={combobox}
    />
  );
}

/** Operator picker — free text with suggestions (no list endpoint exists). */
export function OperatorSelect({ value, onChange, label = 'Operator', w = 150, options }: {
  value: string; onChange: (v: string) => void; label?: string; w?: number; options?: string[];
}) {
  const data = options && options.length ? options : Array.from({ length: 8 }, (_, i) => `op${i + 1}`);
  const combobox = useCombobox();
  return (
    <Autocomplete
      label={label} data={data} value={value} onChange={onChange} w={w} size="sm"
      placeholder="op1" comboboxProps={combobox}
    />
  );
}
