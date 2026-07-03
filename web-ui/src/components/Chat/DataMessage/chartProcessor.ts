// Pure-function adapter: rows + edit state → Chart.js dataset shape.

import type { ChartEditState } from '../../../stores/charts';
import type { DataColumn } from '../../../types';

export interface ProcessedChart {
  labels: any[];
  datasets: Array<{
    label: string;
    data: any[];
    backgroundColor?: string;
    borderColor?: string;
    fill?: boolean;
    /** Per-series render type — set for combo (mixed bar+line) charts. */
    type?: 'bar' | 'line';
    /** Right-hand axis binding — 'y1' for secondary-axis series, else default. */
    yAxisID?: string;
    /** Series key → unit label, forwarded so tooltips can suffix values. */
    unit?: string;
  }>;
  /** True when any series is pinned to the secondary (right-hand) axis. */
  hasSecondaryAxis: boolean;
}

export type ProcessorResult =
  | { ok: true; chart: ProcessedChart }
  | { ok: false; error: string };

export function processChart(
  rows: Record<string, any>[],
  _columns: DataColumn[],
  state: ChartEditState
): ProcessorResult {
  try {
    if (!state.xField) return { ok: false, error: 'No x-axis field selected' };
    if (!state.yFields || state.yFields.length === 0) {
      return { ok: false, error: 'No y-axis fields selected' };
    }

    const safeRows = rows ?? [];
    if (safeRows.length === 0) {
      return { ok: false, error: 'No data to display' };
    }

    const isCombo = state.chartType === 'combo';
    const secondary = new Set(state.secondaryAxis ?? []);
    let hasSecondaryAxis = false;

    const labels = safeRows.map((r) => r[state.xField]);
    const datasets = state.yFields.map((y) => {
      const color = state.seriesColors[y];
      const onSecondary = secondary.has(y);
      if (onSecondary) hasSecondaryAxis = true;
      // For combo charts each series renders as its own type (default line);
      // other chart types leave `type` unset and use the top-level chart type.
      const seriesType = isCombo ? (state.combo?.[y] ?? 'line') : undefined;
      return {
        label: state.seriesLabels[y] ?? y,
        data: safeRows.map((r) => r[y]),
        backgroundColor: color,
        borderColor: color,
        fill: state.chartType === 'area',
        ...(seriesType ? { type: seriesType } : {}),
        ...(onSecondary ? { yAxisID: 'y1' } : {}),
        ...(state.units?.[y] ? { unit: state.units[y] } : {}),
      };
    });

    return { ok: true, chart: { labels, datasets, hasSecondaryAxis } };
  } catch (err: any) {
    return { ok: false, error: err?.message ?? String(err) };
  }
}
