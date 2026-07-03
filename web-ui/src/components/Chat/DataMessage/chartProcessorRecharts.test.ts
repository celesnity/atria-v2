import { describe, it, expect } from 'vitest';
import { processChartRecharts } from './chartProcessorRecharts';
import type { ChartEditState } from '../../../stores/charts';
import type { DataColumn } from '../../../types';

const columns: DataColumn[] = [
  { name: 'region', type: 'string' },
  { name: 'sales', type: 'number' },
  { name: 'units', type: 'number' },
];

const rows = [
  { region: 'N', sales: 100, units: 10 },
  { region: 'S', sales: 200, units: 20 },
];

function baseState(overrides: Partial<ChartEditState> = {}): ChartEditState {
  return {
    activeSuggestionIdx: 0,
    chartType: 'bar',
    xField: 'region',
    yFields: ['sales'],
    title: '',
    subtitle: '',
    axisLabels: {},
    seriesLabels: { sales: 'sales' },
    valueLabels: {},
    seriesColors: { sales: '#3b82f6' },
    combo: {},
    secondaryAxis: [],
    units: {},
    normalized: false,
    legend: true,
    grid: true,
    numberFormat: 'plain',
    ...overrides,
  };
}

describe('processChartRecharts', () => {
  it('produces row-record data + a single series for a bar chart', () => {
    const r = processChartRecharts(rows, columns, baseState());
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.chart.xKey).toBe('region');
    expect(r.chart.data).toEqual([
      { region: 'N', sales: 100 },
      { region: 'S', sales: 200 },
    ]);
    expect(r.chart.series).toHaveLength(1);
    expect(r.chart.series[0]).toMatchObject({ key: 'sales', label: 'sales', renderAs: 'bar', axis: 'left' });
    expect(r.chart.isCircular).toBe(false);
  });

  it('uses seriesLabels for the series label', () => {
    const r = processChartRecharts(rows, columns, baseState({ seriesLabels: { sales: 'Revenue (USD)' } }));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.chart.series[0].label).toBe('Revenue (USD)');
  });

  it('marks area chart series as renderAs=area', () => {
    const r = processChartRecharts(rows, columns, baseState({ chartType: 'area' }));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.chart.series[0].renderAs).toBe('area');
  });

  it('flags circular for pie/doughnut', () => {
    const r = processChartRecharts(rows, columns, baseState({ chartType: 'doughnut' }));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.chart.isCircular).toBe(true);
  });

  it('renders multiple series', () => {
    const r = processChartRecharts(
      rows,
      columns,
      baseState({
        yFields: ['sales', 'units'],
        seriesLabels: { sales: 'sales', units: 'units' },
        seriesColors: { sales: '#3b82f6', units: '#ef4444' },
      })
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.chart.series).toHaveLength(2);
    expect(r.chart.data[1]).toEqual({ region: 'S', sales: 200, units: 20 });
  });

  it('assigns per-series renderAs + right axis for combo with secondary axis', () => {
    const r = processChartRecharts(
      rows,
      columns,
      baseState({
        chartType: 'combo',
        yFields: ['sales', 'units'],
        seriesLabels: { sales: 'sales', units: 'units' },
        seriesColors: { sales: '#3b82f6', units: '#ef4444' },
        combo: { sales: 'bar', units: 'line' },
        secondaryAxis: ['units'],
        units: { units: 'k' },
      })
    );
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.chart.hasSecondaryAxis).toBe(true);
    expect(r.chart.series[0]).toMatchObject({ renderAs: 'bar', axis: 'left' });
    expect(r.chart.series[1]).toMatchObject({ renderAs: 'line', axis: 'right', unit: 'k' });
  });

  it('applies valueLabels to the x-axis category', () => {
    const r = processChartRecharts(rows, columns, baseState({ valueLabels: { N: 'North', S: 'South' } }));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.chart.data.map((d) => d.region)).toEqual(['North', 'South']);
  });

  it('normalizes series to 0-100 when normalized', () => {
    const r = processChartRecharts(rows, columns, baseState({ normalized: true }));
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    // sales max is 200 → [50, 100]
    expect(r.chart.data.map((d) => d.sales)).toEqual([50, 100]);
  });

  it('returns ok:false on empty rows / missing fields', () => {
    expect(processChartRecharts([], columns, baseState()).ok).toBe(false);
    expect(processChartRecharts(rows, columns, baseState({ xField: '' })).ok).toBe(false);
    expect(processChartRecharts(rows, columns, baseState({ yFields: [] })).ok).toBe(false);
  });
});
