import { useMemo, type ReactNode } from 'react';
import {
  X, BarChart3, LineChart, AreaChart, PieChart, CircleDashed,
  ScatterChart, Radar, Combine,
} from 'lucide-react';
import type { DataColumn } from '../../../types';
import {
  useChartsStore,
  DEFAULT_COLORS,
  type ChartType,
  type NumberFormat,
} from '../../../stores/charts';

interface EditPanelProps {
  messageId: string;
  columns: DataColumn[];
  rows: Record<string, any>[];
  onClose: () => void;
}

const CHART_META: { t: ChartType; Icon: typeof BarChart3; label: string }[] = [
  { t: 'bar', Icon: BarChart3, label: 'Bar' },
  { t: 'line', Icon: LineChart, label: 'Line' },
  { t: 'area', Icon: AreaChart, label: 'Area' },
  { t: 'combo', Icon: Combine, label: 'Combo' },
  { t: 'pie', Icon: PieChart, label: 'Pie' },
  { t: 'doughnut', Icon: CircleDashed, label: 'Donut' },
  { t: 'scatter', Icon: ScatterChart, label: 'Scatter' },
  { t: 'radar', Icon: Radar, label: 'Radar' },
];

const NUMBER_FORMATS: { v: NumberFormat; label: string }[] = [
  { v: 'plain', label: 'Plain (1234)' },
  { v: 'thousands', label: 'Grouped (1,234)' },
  { v: 'percent', label: 'Percent (12.3%)' },
  { v: 'currency', label: 'Currency ($)' },
];

const INPUT_CLS =
  'w-full px-2.5 py-1.5 rounded-md bg-canvas border border-hairline-soft text-ink text-[13px] ' +
  'placeholder:text-text-muted/70 focus:outline-none focus:border-accent-cobalt ' +
  'focus:ring-1 focus:ring-accent-cobalt/40 transition-colors';

function update(messageId: string, partial: any) {
  useChartsStore.getState().update(messageId, partial);
}

/** A column is numeric when most of its sampled non-empty values parse as numbers.
 *  CSV columns arrive typed as 'string', so we infer from the data instead. */
function inferNumericColumns(columns: DataColumn[], rows: Record<string, any>[]): string[] {
  const sample = rows.slice(0, 40);
  return columns
    .filter((c) => {
      if (c.type === 'number') return true;
      let seen = 0;
      let numeric = 0;
      for (const r of sample) {
        const v = r[c.name];
        if (v === null || v === undefined || v === '') continue;
        seen++;
        if (Number.isFinite(Number(v))) numeric++;
      }
      return seen > 0 && numeric / seen >= 0.8;
    })
    .map((c) => c.name);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="pt-3 mt-3 border-t border-hairline-soft first:pt-0 first:mt-0 first:border-t-0">
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-2">{title}</h4>
      <div className="space-y-2.5">{children}</div>
    </section>
  );
}

function FieldLabel({ children }: { children: ReactNode }) {
  return <span className="block text-[11px] font-medium text-text-secondary mb-1">{children}</span>;
}

function Toggle({
  checked, onChange, label,
}: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex items-center gap-2 cursor-pointer focus-visible:outline-none focus-visible:shadow-focus-ring rounded"
    >
      <span
        className={`relative w-8 h-[18px] rounded-full transition-colors duration-fast shrink-0 ${
          checked ? 'bg-accent-cobalt' : 'bg-hairline'
        }`}
      >
        <span
          className={`absolute top-0.5 left-0.5 w-[14px] h-[14px] rounded-full bg-white shadow-sm transition-transform duration-fast ${
            checked ? 'translate-x-[14px]' : ''
          }`}
        />
      </span>
      <span className="text-[13px] text-ink">{label}</span>
    </button>
  );
}

export function EditPanel({ messageId, columns, rows, onClose }: EditPanelProps) {
  const state = useChartsStore((s) => s.states[messageId]);
  const xOptions = useMemo(() => columns.map((c) => c.name), [columns]);
  const yOptions = useMemo(() => inferNumericColumns(columns, rows), [columns, rows]);
  const xValues = useMemo(
    () =>
      state
        ? Array.from(new Set(rows.map((r) => String(r[state.xField] ?? '')).filter(Boolean))).slice(0, 50)
        : [],
    [rows, state?.xField]
  );

  if (!state) return null;

  const isCircular = state.chartType === 'pie' || state.chartType === 'doughnut';

  const toggleY = (name: string) => {
    const next = state.yFields.includes(name)
      ? state.yFields.filter((y) => y !== name)
      : [...state.yFields, name];
    const seriesLabels = { ...state.seriesLabels };
    const seriesColors = { ...state.seriesColors };
    if (!seriesLabels[name]) seriesLabels[name] = name;
    if (!seriesColors[name]) seriesColors[name] = DEFAULT_COLORS[next.length % DEFAULT_COLORS.length];
    update(messageId, { yFields: next, seriesLabels, seriesColors });
  };

  return (
    <div className="w-80 max-w-[92vw] rounded-xl border border-hairline-soft bg-surface-soft shadow-xl text-sm overflow-hidden">
      {/* Header (sticky) */}
      <div className="sticky top-0 z-10 flex items-center justify-between px-3.5 py-2.5 border-b border-hairline-soft bg-surface-soft">
        <span className="font-semibold text-ink">Edit chart</span>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-ink leading-none cursor-pointer rounded p-0.5 hover:bg-ink/5 transition-colors focus-visible:outline-none focus-visible:shadow-focus-ring"
          aria-label="Close"
        >
          <X className="w-4 h-4" strokeWidth={2} aria-hidden="true" />
        </button>
      </div>

      {/* Body */}
      <div className="px-3.5 py-3 max-h-[68vh] overflow-y-auto">
        {/* ── Chart type ─────────────────────────────────────────────── */}
        <Section title="Chart type">
          <div className="grid grid-cols-4 gap-1.5">
            {CHART_META.map(({ t, Icon, label }) => {
              const active = state.chartType === t;
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => update(messageId, { chartType: t })}
                  aria-pressed={active}
                  title={label}
                  className={`flex flex-col items-center gap-1 py-2 rounded-md border transition-colors duration-fast cursor-pointer focus-visible:outline-none focus-visible:shadow-focus-ring ${
                    active
                      ? 'border-accent-cobalt bg-accent-cobalt/10 text-accent-cobalt'
                      : 'border-hairline-soft text-text-muted hover:bg-ink/5 hover:text-ink'
                  }`}
                >
                  <Icon className="w-4 h-4" strokeWidth={2} aria-hidden="true" />
                  <span className="text-[10px] font-medium">{label}</span>
                </button>
              );
            })}
          </div>
        </Section>

        {/* ── Labels ─────────────────────────────────────────────────── */}
        <Section title="Labels">
          <label className="block">
            <FieldLabel>Title</FieldLabel>
            <input
              type="text"
              value={state.title}
              placeholder="Chart title"
              onChange={(e) => update(messageId, { title: e.target.value })}
              className={INPUT_CLS}
            />
          </label>
          <label className="block">
            <FieldLabel>Subtitle</FieldLabel>
            <input
              type="text"
              value={state.subtitle}
              placeholder="Optional caption"
              onChange={(e) => update(messageId, { subtitle: e.target.value })}
              className={INPUT_CLS}
            />
          </label>
        </Section>

        {/* ── Axes ───────────────────────────────────────────────────── */}
        <Section title={isCircular ? 'Category & value' : 'Axes'}>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <FieldLabel>{isCircular ? 'Category field' : 'X field'}</FieldLabel>
              <select
                value={state.xField}
                onChange={(e) => update(messageId, { xField: e.target.value })}
                className={INPUT_CLS}
              >
                {xOptions.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            {!isCircular && (
              <label className="block">
                <FieldLabel>X label</FieldLabel>
                <input
                  type="text"
                  value={state.axisLabels.x ?? ''}
                  placeholder={state.xField}
                  onChange={(e) =>
                    update(messageId, { axisLabels: { ...state.axisLabels, x: e.target.value } })
                  }
                  className={INPUT_CLS}
                />
              </label>
            )}
            {!isCircular && (
              <label className="block">
                <FieldLabel>Y label</FieldLabel>
                <input
                  type="text"
                  value={state.axisLabels.y ?? ''}
                  placeholder="e.g. USD, %"
                  onChange={(e) =>
                    update(messageId, { axisLabels: { ...state.axisLabels, y: e.target.value } })
                  }
                  className={INPUT_CLS}
                />
              </label>
            )}
            <label className="block">
              <FieldLabel>Number format</FieldLabel>
              <select
                value={state.numberFormat}
                onChange={(e) => update(messageId, { numberFormat: e.target.value as NumberFormat })}
                className={INPUT_CLS}
              >
                {NUMBER_FORMATS.map((n) => (
                  <option key={n.v} value={n.v}>{n.label}</option>
                ))}
              </select>
            </label>
          </div>
        </Section>

        {/* ── Series ─────────────────────────────────────────────────── */}
        <Section title={isCircular ? 'Value series' : 'Series & colors'}>
          {yOptions.length === 0 ? (
            <p className="text-[12px] text-text-muted italic">No numeric columns detected in this data.</p>
          ) : (
            <div className="space-y-1.5 max-h-52 overflow-y-auto pr-0.5 -mr-0.5">
              {yOptions.map((name) => {
                const active = state.yFields.includes(name);
                return (
                  <div
                    key={name}
                    className={`flex items-center gap-2 rounded-md px-1 py-0.5 transition-colors ${
                      active ? '' : 'opacity-55'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={active}
                      onChange={() => toggleY(name)}
                      aria-label={`Show ${name}`}
                      className="shrink-0 w-3.5 h-3.5 accent-accent-cobalt cursor-pointer"
                    />
                    <label className="relative shrink-0 cursor-pointer" title="Series color">
                      <span
                        className="block w-5 h-5 rounded-md border border-hairline"
                        style={{ background: state.seriesColors[name] ?? DEFAULT_COLORS[0] }}
                      />
                      <input
                        type="color"
                        value={state.seriesColors[name] ?? DEFAULT_COLORS[0]}
                        onChange={(e) =>
                          update(messageId, {
                            seriesColors: { ...state.seriesColors, [name]: e.target.value },
                          })
                        }
                        className="absolute inset-0 opacity-0 cursor-pointer"
                        disabled={!active}
                      />
                    </label>
                    <input
                      type="text"
                      value={state.seriesLabels[name] ?? name}
                      placeholder={name}
                      onChange={(e) =>
                        update(messageId, {
                          seriesLabels: { ...state.seriesLabels, [name]: e.target.value },
                        })
                      }
                      className={`${INPUT_CLS} flex-1 min-w-0 py-1`}
                      disabled={!active}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </Section>

        {/* ── Category labels ────────────────────────────────────────── */}
        {xValues.length > 0 && (
          <Section title={`${isCircular ? 'Slice' : 'Category'} labels`}>
            <div className="space-y-1.5 max-h-44 overflow-y-auto pr-0.5 -mr-0.5">
              {xValues.map((v) => (
                <div key={v} className="flex items-center gap-2">
                  <span className="w-16 shrink-0 truncate text-[11px] text-text-muted" title={v}>{v}</span>
                  <input
                    type="text"
                    value={state.valueLabels[v] ?? ''}
                    placeholder={v}
                    onChange={(e) =>
                      update(messageId, { valueLabels: { ...state.valueLabels, [v]: e.target.value } })
                    }
                    className={`${INPUT_CLS} flex-1 min-w-0 py-1`}
                  />
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Display ────────────────────────────────────────────────── */}
        <Section title="Display">
          <div className="flex items-center gap-6">
            <Toggle checked={state.legend} onChange={(v) => update(messageId, { legend: v })} label="Legend" />
            {!isCircular && (
              <Toggle checked={state.grid} onChange={(v) => update(messageId, { grid: v })} label="Grid" />
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}
