import { forwardRef, useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  BarController,
  LineController,
  RadarController,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Bar, Line, Pie, Doughnut, Scatter, Radar, Chart } from 'react-chartjs-2';
import type { ChartType, NumberFormat } from '../../../stores/charts';
import type { ProcessedChart } from './chartProcessor';

ChartJS.register(
  CategoryScale,
  LinearScale,
  RadialLinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  BarController,
  LineController,
  RadarController,
  Title,
  Tooltip,
  Legend,
  Filler
);

const usdFmt = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});
const thouFmt = new Intl.NumberFormat('en-US');

function formatValue(v: number | null | undefined, fmt: NumberFormat): string {
  if (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) return '';
  const n = typeof v === 'number' ? v : Number(v);
  if (isNaN(n)) return String(v);
  switch (fmt) {
    case 'thousands':
      return thouFmt.format(n);
    case 'percent':
      return `${(n * 100).toFixed(2)}%`;
    case 'currency':
      return usdFmt.format(n);
    case 'plain':
    default:
      return String(n);
  }
}

interface ChartViewProps {
  chart: ProcessedChart;
  chartType: ChartType;
  title: string;
  axisLabels: { x?: string; y?: string };
  legend: boolean;
  grid: boolean;
  numberFormat: NumberFormat;
}

export const ChartView = forwardRef<any, ChartViewProps>(function ChartView(
  { chart, chartType, title, axisLabels, legend, grid, numberFormat },
  ref
) {
  const data = useMemo(
    () => ({
      labels: chart.labels,
      datasets: chart.datasets,
    }),
    [chart]
  );

  const isCircular = chartType === 'pie' || chartType === 'doughnut';
  const isRadar = chartType === 'radar';
  const isCombo = chartType === 'combo';
  const hasSecondaryAxis = chart.hasSecondaryAxis;

  const withUnit = (value: string, unit?: string) =>
    unit ? `${value} ${unit}` : value;

  const options = useMemo<any>(() => {
    const base: any = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: title
          ? { display: true, text: title, color: '#e5e7eb' }
          : { display: false },
        legend: { display: legend, labels: { color: '#cbd5e1' } },
        tooltip: {
          callbacks: {
            label: (ctx: any) => {
              const lbl = ctx.dataset?.label ? `${ctx.dataset.label}: ` : '';
              const raw = ctx.parsed?.y ?? ctx.parsed?.r ?? ctx.parsed ?? ctx.raw;
              const unit = ctx.dataset?.unit as string | undefined;
              return `${lbl}${withUnit(formatValue(raw as number, numberFormat), unit)}`;
            },
          },
        },
      },
    };
    if (isRadar) {
      base.scales = {
        r: {
          grid: { display: grid, color: 'rgba(148,163,184,0.15)' },
          angleLines: { color: 'rgba(148,163,184,0.15)' },
          pointLabels: { color: '#cbd5e1' },
          ticks: {
            color: '#94a3b8',
            backdropColor: 'transparent',
            callback: (val: any) => formatValue(val as number, numberFormat),
          },
        },
      };
    } else if (!isCircular) {
      base.scales = {
        x: {
          title: axisLabels.x
            ? { display: true, text: axisLabels.x, color: '#cbd5e1' }
            : { display: false },
          grid: { display: grid, color: 'rgba(148,163,184,0.12)' },
          ticks: { color: '#94a3b8' },
        },
        y: {
          type: 'linear',
          position: 'left',
          title: axisLabels.y
            ? { display: true, text: axisLabels.y, color: '#cbd5e1' }
            : { display: false },
          grid: { display: grid, color: 'rgba(148,163,184,0.12)' },
          ticks: {
            color: '#94a3b8',
            callback: (val: any) => formatValue(val as number, numberFormat),
          },
        },
      };
      if (hasSecondaryAxis) {
        // Right-hand axis for combo/secondary-axis series; no gridlines so it
        // doesn't clash with the primary axis grid.
        base.scales.y1 = {
          type: 'linear',
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: {
            color: '#94a3b8',
            callback: (val: any) => formatValue(val as number, numberFormat),
          },
        };
      }
    }
    return base;
  }, [title, legend, grid, axisLabels.x, axisLabels.y, numberFormat, isCircular, isRadar, hasSecondaryAxis]);

  // scatter expects {x,y} points
  const scatterData = useMemo(() => {
    if (chartType !== 'scatter') return data;
    return {
      datasets: chart.datasets.map((ds) => ({
        ...ds,
        data: ds.data.map((y, i) => ({ x: chart.labels[i], y })),
      })),
    };
  }, [chartType, chart, data]);

  // For combo charts each dataset carries its own `type`; give the base a type so
  // Chart.js can mix. Bars render behind lines by default.
  const comboData = useMemo(() => {
    if (!isCombo) return data;
    return {
      labels: chart.labels,
      datasets: chart.datasets.map((ds) => ({
        ...ds,
        type: ds.type ?? 'bar',
      })),
    };
  }, [isCombo, chart, data]);

  const chartProps: any = { ref: ref as any, data, options };
  return (
    <div style={{ height: 360 }} className="w-full">
      {chartType === 'bar' && <Bar key="bar" {...chartProps} />}
      {chartType === 'line' && <Line key="line" {...chartProps} />}
      {chartType === 'area' && <Line key="area" {...chartProps} />}
      {chartType === 'pie' && <Pie key="pie" {...chartProps} />}
      {chartType === 'doughnut' && <Doughnut key="doughnut" {...chartProps} />}
      {chartType === 'radar' && <Radar key="radar" {...chartProps} />}
      {chartType === 'combo' && (
        <Chart key="combo" type="bar" ref={ref as any} data={comboData as any} options={options} />
      )}
      {chartType === 'scatter' && (
        <Scatter key="scatter" ref={ref as any} data={scatterData as any} options={options} />
      )}
    </div>
  );
});
