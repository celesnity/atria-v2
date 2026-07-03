import type { RefObject } from 'react';
import type { DataColumn } from '../../../types';
import {
  useChartsStore,
  type ChartType,
  type NumberFormat,
} from '../../../stores/charts';

interface EditPanelProps {
  messageId: string;
  columns: DataColumn[];
  chartRef: RefObject<any>;
  onClose: () => void;
}

const CHART_TYPES: ChartType[] = ['bar', 'line', 'area', 'pie', 'doughnut', 'scatter', 'combo', 'radar'];
const NUMBER_FORMATS: NumberFormat[] = ['plain', 'thousands', 'percent', 'currency'];

function update(messageId: string, partial: any) {
  useChartsStore.getState().update(messageId, partial);
}

function downloadPNG(chartRef: RefObject<any>, filename: string) {
  const chart = chartRef.current;
  if (!chart || typeof chart.toBase64Image !== 'function') return;
  const url = chart.toBase64Image();
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
}

export function EditPanel({ messageId, columns, chartRef, onClose }: EditPanelProps) {
  const state = useChartsStore((s) => s.states[messageId]);
  if (!state) return null;

  const xOptions = columns.map((c) => c.name);
  const yOptions = columns.filter((c) => c.type === 'number').map((c) => c.name);

  const toggleY = (name: string) => {
    const next = state.yFields.includes(name)
      ? state.yFields.filter((y) => y !== name)
      : [...state.yFields, name];
    // Ensure new y has default label/color
    const seriesLabels = { ...state.seriesLabels };
    const seriesColors = { ...state.seriesColors };
    if (!seriesLabels[name]) seriesLabels[name] = name;
    if (!seriesColors[name]) seriesColors[name] = '#3b82f6';
    update(messageId, { yFields: next, seriesLabels, seriesColors });
  };

  return (
    <div className="w-72 max-w-[90vw] rounded-lg border border-border-300/15 bg-bg-100 shadow-xl text-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-300/15">
        <span className="font-semibold text-text-000">Edit chart</span>
        <button
          onClick={onClose}
          className="text-text-300 hover:text-text-000 text-base leading-none"
          aria-label="Close"
        >
          ×
        </button>
      </div>

      {/* Body */}
      <div className="px-3 py-3 space-y-3 max-h-[70vh] overflow-y-auto">
        {/* Chart type */}
        <label className="block">
          <span className="block text-xs text-text-300 mb-1">Chart type</span>
          <select
            value={state.chartType}
            onChange={(e) => update(messageId, { chartType: e.target.value as ChartType })}
            className="w-full px-2 py-1 rounded bg-bg-000 border border-border-300/15 text-text-100"
          >
            {CHART_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>

        {/* Title */}
        <label className="block">
          <span className="block text-xs text-text-300 mb-1">Title</span>
          <input
            type="text"
            value={state.title}
            onChange={(e) => update(messageId, { title: e.target.value })}
            className="w-full px-2 py-1 rounded bg-bg-000 border border-border-300/15 text-text-100"
          />
        </label>

        {/* X axis */}
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="block text-xs text-text-300 mb-1">X field</span>
            <select
              value={state.xField}
              onChange={(e) => update(messageId, { xField: e.target.value })}
              className="w-full px-2 py-1 rounded bg-bg-000 border border-border-300/15 text-text-100"
            >
              {xOptions.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="block text-xs text-text-300 mb-1">X label</span>
            <input
              type="text"
              value={state.axisLabels.x ?? ''}
              placeholder={state.xField}
              onChange={(e) =>
                update(messageId, { axisLabels: { ...state.axisLabels, x: e.target.value } })
              }
              className="w-full px-2 py-1 rounded bg-bg-000 border border-border-300/15 text-text-100"
            />
          </label>
        </div>

        {/* Y label */}
        <label className="block">
          <span className="block text-xs text-text-300 mb-1">Y label (unit)</span>
          <input
            type="text"
            value={state.axisLabels.y ?? ''}
            placeholder="e.g. USD, %, count"
            onChange={(e) =>
              update(messageId, { axisLabels: { ...state.axisLabels, y: e.target.value } })
            }
            className="w-full px-2 py-1 rounded bg-bg-000 border border-border-300/15 text-text-100"
          />
        </label>

        {/* Number format */}
        <label className="block">
          <span className="block text-xs text-text-300 mb-1">Number format</span>
          <select
            value={state.numberFormat}
            onChange={(e) => update(messageId, { numberFormat: e.target.value as NumberFormat })}
            className="w-full px-2 py-1 rounded bg-bg-000 border border-border-300/15 text-text-100"
          >
            {NUMBER_FORMATS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        {/* Series */}
        <div>
          <span className="block text-xs text-text-300 mb-1">Series</span>
          <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
            {yOptions.map((name) => {
              const active = state.yFields.includes(name);
              return (
                <div key={name} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={() => toggleY(name)}
                    className="shrink-0"
                  />
                  <input
                    type="color"
                    value={state.seriesColors[name] ?? '#3b82f6'}
                    onChange={(e) =>
                      update(messageId, {
                        seriesColors: { ...state.seriesColors, [name]: e.target.value },
                      })
                    }
                    className="w-6 h-6 shrink-0 rounded border border-border-300/15 bg-bg-000"
                    disabled={!active}
                  />
                  <input
                    type="text"
                    value={state.seriesLabels[name] ?? name}
                    placeholder={name}
                    onChange={(e) =>
                      update(messageId, {
                        seriesLabels: { ...state.seriesLabels, [name]: e.target.value },
                      })
                    }
                    className="flex-1 min-w-0 px-2 py-1 rounded bg-bg-000 border border-border-300/15 text-text-100"
                    disabled={!active}
                  />
                </div>
              );
            })}
            {yOptions.length === 0 && (
              <div className="text-xs text-text-400 italic">No numeric columns available.</div>
            )}
          </div>
        </div>

        {/* Toggles */}
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 text-text-100">
            <input
              type="checkbox"
              checked={state.legend}
              onChange={(e) => update(messageId, { legend: e.target.checked })}
            />
            <span>Legend</span>
          </label>
          <label className="flex items-center gap-1.5 text-text-100">
            <input
              type="checkbox"
              checked={state.grid}
              onChange={(e) => update(messageId, { grid: e.target.checked })}
            />
            <span>Grid</span>
          </label>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-end gap-2 px-3 py-2 border-t border-border-300/15">
        <button
          onClick={() => downloadPNG(chartRef, `${state.title || 'chart'}.png`)}
          className="px-2 py-1 text-xs rounded border border-border-300/15 text-text-100 hover:bg-bg-200"
        >
          Download PNG
        </button>
      </div>
    </div>
  );
}
