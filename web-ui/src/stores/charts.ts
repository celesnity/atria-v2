import { create } from 'zustand';
import type { ChartSuggestion, DataColumn } from '../types';

export type ChartType =
  | 'bar' | 'line' | 'area' | 'pie' | 'doughnut' | 'scatter' | 'combo' | 'radar';
export type NumberFormat = 'plain' | 'thousands' | 'percent' | 'currency';

export interface ChartEditState {
  activeSuggestionIdx: number;
  chartType: ChartType;
  xField: string;
  yFields: string[];
  title: string;
  subtitle: string;
  description?: string;
  axisLabels: { x?: string; y?: string };
  seriesLabels: Record<string, string>;
  /** X-axis category value → display override (e.g. "A" → "Product Alpha"). */
  valueLabels: Record<string, string>;
  seriesColors: Record<string, string>;
  /** Series key → 'bar'|'line' for a mixed (combo) chart. */
  combo: Record<string, 'bar' | 'line'>;
  /** Series keys bound to the right-hand y-axis. */
  secondaryAxis: string[];
  /** Series key → unit label; drives axis + tooltip suffix. */
  units: Record<string, string>;
  /** True for 0–100 normalized radar values. */
  normalized: boolean;
  legend: boolean;
  grid: boolean;
  numberFormat: NumberFormat;
}

/** User-intent fields persisted across reload (not derived data). */
export type ChartOverrides = Pick<
  ChartEditState,
  | 'activeSuggestionIdx'
  | 'chartType'
  | 'title'
  | 'subtitle'
  | 'axisLabels'
  | 'seriesLabels'
  | 'valueLabels'
  | 'seriesColors'
  | 'legend'
  | 'grid'
  | 'numberFormat'
>;

const OVERRIDE_KEYS: (keyof ChartOverrides)[] = [
  'activeSuggestionIdx', 'chartType', 'title', 'subtitle', 'axisLabels',
  'seriesLabels', 'valueLabels', 'seriesColors', 'legend', 'grid', 'numberFormat',
];

/** Pull the persistable slice out of a full chart edit state. */
export function extractOverrides(state: ChartEditState): ChartOverrides {
  const out = {} as ChartOverrides;
  for (const k of OVERRIDE_KEYS) (out as any)[k] = (state as any)[k];
  return out;
}

interface ChartsStore {
  states: Record<string, ChartEditState>;
  initFromSuggestion: (
    messageId: string,
    suggestions: ChartSuggestion[],
    columns: DataColumn[],
    idx: number,
    overrides?: Partial<ChartOverrides> | null
  ) => void;
  update: (messageId: string, partial: Partial<ChartEditState>) => void;
  reset: (messageId: string) => void;
}

// Categorical series palette aligned with the brand accent spine
// (cobalt → violet → magenta) plus semantic + supporting hues, tuned for
// contrast on the dark/light surface-soft card.
export const DEFAULT_COLORS = ['#2f5fe0','#b264d9','#4cc98a','#ee6a4f','#7b3fe4','#e0a53f','#38bdb0','#e05fa8'];

function buildState(suggestions: ChartSuggestion[], _columns: DataColumn[], idx: number): ChartEditState {
  const s = suggestions[idx] ?? suggestions[0];
  const seriesColors: Record<string, string> = {};
  const seriesLabels: Record<string, string> = {};
  s.y.forEach((y, i) => {
    seriesColors[y] = DEFAULT_COLORS[i % DEFAULT_COLORS.length];
    // Prefer the suggestion's display name for this series, falling back to the key.
    seriesLabels[y] = s.labels?.[y] ?? y;
  });
  return {
    activeSuggestionIdx: idx,
    chartType: s.chart_type,
    xField: s.x,
    yFields: [...s.y],
    title: s.title ?? '',
    subtitle: '',
    description: s.description,
    axisLabels: {},
    seriesLabels,
    valueLabels: {},
    seriesColors,
    combo: s.combo ?? {},
    secondaryAxis: s.secondaryAxis ?? [],
    units: s.units ?? {},
    normalized: s.normalized ?? false,
    legend: true,
    grid: true,
    numberFormat: 'plain',
  };
}

export const useChartsStore = create<ChartsStore>((set) => ({
  states: {},
  initFromSuggestion: (messageId, suggestions, columns, idx, overrides) =>
    set((state) => {
      // Saved overrides may re-point the active suggestion; honor that first so
      // the base chart type/series match what the user last saw.
      const effectiveIdx =
        overrides && typeof overrides.activeSuggestionIdx === 'number'
          ? overrides.activeSuggestionIdx
          : idx;
      const base = buildState(suggestions, columns, effectiveIdx);
      return {
        states: {
          ...state.states,
          [messageId]: overrides ? { ...base, ...overrides } : base,
        },
      };
    }),
  update: (messageId, partial) =>
    set((state) => {
      const prev = state.states[messageId];
      if (!prev) return state;
      return { states: { ...state.states, [messageId]: { ...prev, ...partial } } };
    }),
  reset: (messageId) =>
    set((state) => {
      const { [messageId]: _drop, ...rest } = state.states;
      return { states: rest };
    }),
}));
