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
  description?: string;
  axisLabels: { x?: string; y?: string };
  seriesLabels: Record<string, string>;
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

interface ChartsStore {
  states: Record<string, ChartEditState>;
  initFromSuggestion: (
    messageId: string,
    suggestions: ChartSuggestion[],
    columns: DataColumn[],
    idx: number
  ) => void;
  update: (messageId: string, partial: Partial<ChartEditState>) => void;
  reset: (messageId: string) => void;
}

export const DEFAULT_COLORS = ['#3b82f6','#ef4444','#10b981','#f59e0b','#8b5cf6','#ec4899','#14b8a6','#f97316'];

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
    description: s.description,
    axisLabels: {},
    seriesLabels,
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
  initFromSuggestion: (messageId, suggestions, columns, idx) =>
    set((state) => ({
      states: { ...state.states, [messageId]: buildState(suggestions, columns, idx) },
    })),
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
