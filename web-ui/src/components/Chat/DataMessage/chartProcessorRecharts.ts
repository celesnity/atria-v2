// Pure-function adapter: rows + edit state → Recharts-ready data + series meta.
//
// Recharts consumes an array of row-records directly (each series reads its own
// `dataKey`), so unlike the Chart.js adapter we pass rows through mostly as-is and
// only compute the per-series descriptors (color, axis, render type) the view needs.

import { DEFAULT_COLORS, type ChartEditState } from '../../../stores/charts';
import type { DataColumn } from '../../../types';

export interface RechartsSeries {
  /** Row key to read the value from. */
  key: string;
  /** Display label (legend / tooltip). */
  label: string;
  color: string;
  /** Y-axis binding: right-hand axis for secondary series, else left. */
  axis: 'left' | 'right';
  /** Per-series render type for combo charts; matches top-level type otherwise. */
  renderAs: 'bar' | 'line' | 'area';
  unit?: string;
}

export interface ProcessedRecharts {
  /** Row-records passed to the Recharts chart component. */
  data: Record<string, unknown>[];
  /** Category / x-axis key. */
  xKey: string;
  series: RechartsSeries[];
  hasSecondaryAxis: boolean;
  /** True for pie/doughnut — the view renders one series as N slices. */
  isCircular: boolean;
}

export type RechartsResult =
  | { ok: true; chart: ProcessedRecharts }
  | { ok: false; error: string };

function baseRenderAs(chartType: ChartEditState['chartType']): 'bar' | 'line' | 'area' {
  if (chartType === 'line' || chartType === 'radar' || chartType === 'scatter') return 'line';
  if (chartType === 'area') return 'area';
  return 'bar';
}

export function processChartRecharts(
  rows: Record<string, any>[],
  _columns: DataColumn[],
  state: ChartEditState
): RechartsResult {
  try {
    if (!state.xField) return { ok: false, error: 'No x-axis field selected' };
    if (!state.yFields || state.yFields.length === 0) {
      return { ok: false, error: 'No y-axis fields selected' };
    }
    const safeRows = rows ?? [];
    if (safeRows.length === 0) return { ok: false, error: 'No data to display' };

    const isCombo = state.chartType === 'combo';
    const isCircular = state.chartType === 'pie' || state.chartType === 'doughnut';
    const secondary = new Set(state.secondaryAxis ?? []);
    let hasSecondaryAxis = false;

    // Normalize each numeric series to 0–100 (radar with mismatched scales).
    const scale: Record<string, number> = {};
    if (state.normalized) {
      for (const y of state.yFields) {
        const max = Math.max(...safeRows.map((r) => Number(r[y]) || 0), 0);
        scale[y] = max > 0 ? max : 1;
      }
    }

    const xKey = state.xField;
    const data = safeRows.map((r) => {
      const rawX = String(r[xKey] ?? '');
      const out: Record<string, unknown> = { [xKey]: state.valueLabels?.[rawX] ?? r[xKey] };
      for (const y of state.yFields) {
        const v = Number(r[y]);
        out[y] = state.normalized && !Number.isNaN(v) ? (v / scale[y]) * 100 : r[y];
      }
      return out;
    });

    const series: RechartsSeries[] = state.yFields.map((y, i) => {
      const onSecondary = secondary.has(y);
      if (onSecondary) hasSecondaryAxis = true;
      const renderAs = isCombo ? (state.combo?.[y] ?? 'line') : baseRenderAs(state.chartType);
      return {
        key: y,
        label: state.seriesLabels[y] ?? y,
        color: state.seriesColors[y] ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length],
        axis: onSecondary ? 'right' : 'left',
        renderAs,
        unit: state.units?.[y],
      };
    });

    return { ok: true, chart: { data, xKey, series, hasSecondaryAxis, isCircular } };
  } catch (err: any) {
    return { ok: false, error: err?.message ?? String(err) };
  }
}
