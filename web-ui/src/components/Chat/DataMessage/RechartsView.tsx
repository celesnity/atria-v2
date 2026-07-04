// Recharts renderer for agent-recommended charts. Maps the processed data +
// edit state onto Recharts primitives. Cartesian types (bar/line/area/combo) all
// go through ComposedChart so a single code path handles mixed render types.

import {
  ResponsiveContainer,
  ComposedChart, Bar, Line, Area,
  PieChart, Pie, Cell,
  ScatterChart, Scatter,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import type { ChartEditState, NumberFormat } from '../../../stores/charts';
import { DEFAULT_COLORS } from '../../../stores/charts';
import type { ProcessedRecharts } from './chartProcessorRecharts';

interface RechartsViewProps {
  processed: ProcessedRecharts;
  state: ChartEditState;
}

function makeFormatter(fmt: NumberFormat, unit?: string) {
  return (value: unknown): string => {
    const n = typeof value === 'number' ? value : Number(value);
    if (Number.isNaN(n)) return String(value ?? '');
    let s: string;
    switch (fmt) {
      case 'thousands': s = n.toLocaleString(); break;
      case 'percent': s = `${n.toFixed(1)}%`; break;
      case 'currency': s = n.toLocaleString(undefined, { style: 'currency', currency: 'USD' }); break;
      default: s = String(n);
    }
    return unit && fmt !== 'currency' && fmt !== 'percent' ? `${s} ${unit}` : s;
  };
}

// Colors are pulled from the app's real design tokens (index.css CSS vars) so
// the chart reads on-brand in both dark and light themes.
const AXIS = { fontSize: 11, fill: 'hsl(var(--text-muted))' };
const GRID_COLOR = 'hsl(var(--hairline) / 0.4)';

const tooltipStyle = {
  contentStyle: {
    background: 'hsl(var(--surface-soft))',
    border: '1px solid hsl(var(--hairline))',
    borderRadius: 8,
    fontSize: 12,
    color: 'hsl(var(--ink))',
  },
  labelStyle: { color: 'hsl(var(--ink))' },
  itemStyle: { color: 'hsl(var(--text-secondary))' },
} as const;

export function RechartsView({ processed, state }: RechartsViewProps) {
  const { data, xKey, series, hasSecondaryAxis, isCircular } = processed;
  const fmt = makeFormatter(state.numberFormat);

  // ── Pie / doughnut ────────────────────────────────────────────────────────
  if (isCircular) {
    const s0 = series[0];
    const innerRadius = state.chartType === 'doughnut' ? 55 : 0;
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey={s0.key}
            nameKey={xKey}
            cx="50%"
            cy="50%"
            outerRadius={100}
            innerRadius={innerRadius}
            label
          >
            {data.map((_, i) => (
              <Cell key={i} fill={DEFAULT_COLORS[i % DEFAULT_COLORS.length]} stroke="hsl(var(--surface-soft))" />
            ))}
          </Pie>
          <Tooltip {...tooltipStyle} formatter={(v) => fmt(v)} />
          {state.legend && <Legend iconType="circle" iconSize={8} />}
        </PieChart>
      </ResponsiveContainer>
    );
  }

  // ── Radar ──────────────────────────────────────────────────────────────────
  if (state.chartType === 'radar') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data}>
          <PolarGrid stroke={GRID_COLOR} />
          <PolarAngleAxis dataKey={xKey} tick={AXIS} />
          <PolarRadiusAxis tick={AXIS} />
          {series.map((s) => (
            <Radar key={s.key} name={s.label} dataKey={s.key} stroke={s.color} fill={s.color} fillOpacity={0.25} />
          ))}
          <Tooltip {...tooltipStyle} formatter={(v) => fmt(v)} />
          {state.legend && <Legend iconType="circle" iconSize={8} />}
        </RadarChart>
      </ResponsiveContainer>
    );
  }

  // ── Scatter ─────────────────────────────────────────────────────────────────
  if (state.chartType === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          {state.grid && <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />}
          <XAxis dataKey={xKey} name={state.axisLabels.x ?? xKey} tick={AXIS} tickLine={false} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt} width={52} />
          <Tooltip {...tooltipStyle} formatter={(v) => fmt(v)} cursor={{ strokeDasharray: '3 3' }} />
          {state.legend && <Legend iconType="circle" iconSize={8} />}
          {series.map((s) => (
            <Scatter key={s.key} name={s.label} dataKey={s.key} fill={s.color} />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  // ── Cartesian: bar / line / area / combo ────────────────────────────────────
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        {state.grid && <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} vertical={false} />}
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis yAxisId="left" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt} width={52} />
        {hasSecondaryAxis && (
          <YAxis yAxisId="right" orientation="right" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt} width={52} />
        )}
        <Tooltip {...tooltipStyle} formatter={(v) => fmt(v)} />
        {state.legend && series.length > 1 && <Legend iconType="circle" iconSize={8} />}
        {series.map((s) => {
          const common = { key: s.key, dataKey: s.key, name: s.label, yAxisId: s.axis } as const;
          if (s.renderAs === 'bar') {
            return <Bar {...common} fill={s.color} radius={[3, 3, 0, 0]} />;
          }
          if (s.renderAs === 'area') {
            return <Area {...common} type="monotone" stroke={s.color} fill={s.color} fillOpacity={0.2} />;
          }
          return <Line {...common} type="monotone" stroke={s.color} strokeWidth={2} dot={false} />;
        })}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
