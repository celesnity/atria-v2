import { useEffect, useState, useCallback, useRef } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useCopyToClipboard } from 'usehooks-ts';
import type { DataColumn, Message } from '../../../types';
import { apiClient } from '../../../api/client';
import { EditableDataTable } from './EditableDataTable';
import { RechartsView } from './RechartsView';
import { EditPanel } from './EditPanel';
import { processChartRecharts } from './chartProcessorRecharts';
import { extractOverrides, useChartsStore, type ChartOverrides } from '../../../stores/charts';
import { useChatStore } from '../../../stores/chat';
import { loadSessionOverrides, saveChartOverridesDebounced } from './chartOverrides';

function SqlDisclosure({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [, copyToClipboard] = useCopyToClipboard();

  const copy = useCallback(async () => {
    const ok = await copyToClipboard(sql);
    if (!ok) return;
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [sql, copyToClipboard]);

  return (
    <div className="border-b border-hairline-soft bg-ink/[0.03]">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 w-full px-3 py-1.5 text-[11px] text-text-muted hover:text-ink"
      >
        <ChevronRight className={`w-3 h-3 shrink-0 transition-transform duration-fast ${open ? 'rotate-90' : ''}`} strokeWidth={2} aria-hidden="true" />
        <span className="font-mono opacity-70">SQL</span>
        <span className="truncate opacity-50 flex-1 text-left">{!open && sql.replace(/\s+/g, ' ').slice(0, 80)}</span>
      </button>
      {open && (
        <div className="relative px-3 pb-3">
          <pre className="text-[11px] font-mono text-text-secondary bg-ink/[0.05] rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
            {sql}
          </pre>
          <button
            onClick={copy}
            className="absolute top-1 right-4 px-1.5 py-0.5 text-[10px] rounded border border-hairline-soft text-text-muted hover:bg-ink/5"
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      )}
    </div>
  );
}

export function DataMessage({ message }: { message: Message }) {
  // Editable variant (send_editable_table): render an inline editable grid bound
  // to the module CSV. Falls through to the read-only renderer if the binding is
  // malformed, so a bad payload never breaks the chat.
  const src = message.data_source;
  if (message.data_editable && src && src.file && (src.module || src.session)) {
    return (
      <EditableDataTable
        messageId={message.data_message_id ?? ''}
        title={message.data_title || 'Data'}
        columns={message.data_columns ?? []}
        rows={message.data_rows ?? []}
        source={src}
        warning={message.data_warning}
      />
    );
  }

  const messageId = message.data_message_id ?? '';

  const [fetchedColumns, setFetchedColumns] = useState<DataColumn[]>(message.data_columns ?? []);
  const [fetchedRows, setFetchedRows] = useState<Record<string, any>[]>(message.data_rows ?? []);
  const [fetchedImageSrc, setFetchedImageSrc] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Lazy-fetch table rows when not embedded in the event
  useEffect(() => {
    if (fetchedRows.length > 0) return;
    if (!message.data_db_path || !message.data_table_name) return;
    apiClient
      .fetchTableData(message.data_db_path, message.data_table_name)
      .then(({ columns, rows }) => {
        setFetchedColumns(columns);
        setFetchedRows(rows);
      })
      .catch((e) => setFetchError(String(e)));
  }, [message.data_db_path, message.data_table_name]);

  // Lazy-fetch chart PNG from disk path (session reload path)
  useEffect(() => {
    if (message.data_image_src || fetchedImageSrc) return;
    if (!message.data_image_path) return;
    apiClient
      .fetchChartImage(message.data_image_path)
      .then(setFetchedImageSrc)
      .catch((e) => setFetchError(String(e)));
  }, [message.data_image_path]);

  const columns = fetchedColumns;
  const rows = fetchedRows;

  const imageSrc = message.data_image_src || fetchedImageSrc || null;
  const hasData = rows.length > 0;

  // Interactive chart (Recharts) rendered from agent-provided suggestions.
  const suggestions = message.data_suggestions ?? [];
  const hasCharts = suggestions.length > 0 && hasData;
  const chartState = useChartsStore((s) => s.states[messageId]);
  const initFromSuggestion = useChartsStore((s) => s.initFromSuggestion);
  const sessionId = useChatStore((s) => s.currentSessionId);
  const [showEdit, setShowEdit] = useState(false);

  // Init the chart edit state once, merging any persisted overrides for this
  // chart_id so a reload restores the user's last edits.
  const initingRef = useRef(false);
  useEffect(() => {
    if (!hasCharts || chartState || initingRef.current) return;
    initingRef.current = true;
    let cancelled = false;
    (async () => {
      let ov: Partial<ChartOverrides> | null = null;
      if (sessionId) {
        const map = await loadSessionOverrides(sessionId);
        ov = map[messageId] ?? null;
      }
      if (!cancelled) initFromSuggestion(messageId, suggestions, columns, 0, ov);
      initingRef.current = false;
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasCharts, !!chartState, messageId, columns.length, suggestions.length, sessionId]);

  // Debounce-persist edits. Skip the first run (the init above) so we only save
  // real user changes, not the freshly-restored defaults.
  const skipSaveRef = useRef(true);
  useEffect(() => {
    if (!chartState || !sessionId) return;
    if (skipSaveRef.current) { skipSaveRef.current = false; return; }
    saveChartOverridesDebounced(sessionId, messageId, extractOverrides(chartState));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartState, sessionId]);

  const [view, setView] = useState<'preview' | 'table' | 'chart'>(
    hasCharts ? 'chart' : imageSrc ? 'preview' : 'table'
  );
  const [collapsed, setCollapsed] = useState(false);
  const TABLE_PAGE = 200;

  // Verbose one-line summary shown under the title: shape · chart type · source.
  const CHART_LABELS: Record<string, string> = {
    bar: 'Bar', line: 'Line', area: 'Area', pie: 'Pie',
    doughnut: 'Doughnut', scatter: 'Scatter', combo: 'Combo', radar: 'Radar',
  };
  const metaParts: string[] = [];
  if (hasData) metaParts.push(`${rows.length.toLocaleString()} rows × ${columns.length} cols`);
  if (view === 'chart' && chartState) {
    metaParts.push(`${CHART_LABELS[chartState.chartType] ?? chartState.chartType} chart`);
  }
  const srcInfo = message.data_source;
  if (srcInfo?.module) metaParts.push(srcInfo.module);
  else if (srcInfo && (srcInfo as any).session) metaParts.push('session data');

  // Auto-switch to preview when image arrives after initial mount
  useEffect(() => {
    if (imageSrc && !hasCharts) setView('preview');
  }, [!!imageSrc]);

  if (fetchError) {
    return (
      <div className="my-3 rounded-lg border border-semantic-danger/30 bg-surface-soft px-3 py-2 text-sm text-semantic-danger">
        Failed to load chart data: {fetchError}
      </div>
    );
  }

  const pendingImageFetch = !!message.data_image_path && !imageSrc && !fetchError;
  const nothingReady = !imageSrc && !hasData && !pendingImageFetch;
  if (!messageId || nothingReady) {
    return (
      <div className="my-3 rounded-lg border border-hairline-soft bg-surface-soft px-3 py-2 text-sm text-text-muted">
        {pendingImageFetch ? (message.data_title || 'Loading chart…') : 'Loading data…'}
      </div>
    );
  }

  return (
    <div className="my-3 relative">
      <div className="rounded-lg border border-hairline-soft bg-surface-soft overflow-hidden">
        {/* Header */}
        <div className={`flex items-center justify-between gap-2 px-3 py-2 ${collapsed ? '' : 'border-b border-hairline-soft'}`}>
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            aria-expanded={!collapsed}
            className="flex items-center gap-2 min-w-0 flex-1 text-left cursor-pointer group focus-visible:outline-none focus-visible:shadow-focus-ring rounded"
          >
            <ChevronDown
              className={`w-3.5 h-3.5 text-text-muted shrink-0 transition-transform duration-fast ${collapsed ? '-rotate-90' : ''}`}
              strokeWidth={2}
              aria-hidden="true"
            />
            <div className="flex flex-col min-w-0">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm font-semibold text-ink truncate group-hover:text-accent-cobalt transition-colors duration-fast">
                  {message.data_title || 'Data'}
                </span>
                {message.data_warning && (
                  <span
                    className="text-[11px] px-1.5 py-0.5 rounded bg-accent-cobalt/10 text-accent-cobalt border border-accent-cobalt/20 shrink-0"
                    title={message.data_warning}
                  >
                    {message.data_warning}
                  </span>
                )}
              </div>
              {metaParts.length > 0 && (
                <span className="text-[11px] text-text-muted truncate font-mono">
                  {metaParts.join(' · ')}
                </span>
              )}
            </div>
          </button>
          <div className="flex items-center gap-1 shrink-0">
            <div className="flex rounded border border-hairline-soft overflow-hidden text-xs">
              {hasCharts && (
                <button
                  onClick={() => setView('chart')}
                  className={`px-2 py-1 ${view === 'chart' ? 'bg-accent-cobalt/15 text-accent-cobalt' : 'text-text-muted hover:bg-ink/5'}`}
                >
                  Chart
                </button>
              )}
              {imageSrc && (
                <button
                  onClick={() => setView('preview')}
                  className={`px-2 py-1 ${imageSrc && hasCharts ? 'border-l border-hairline-soft' : ''} ${view === 'preview' ? 'bg-accent-cobalt/15 text-accent-cobalt' : 'text-text-muted hover:bg-ink/5'}`}
                >
                  Image
                </button>
              )}
              {hasData && (
                <button
                  onClick={() => setView('table')}
                  className={`px-2 py-1 ${(imageSrc || hasCharts) ? 'border-l border-hairline-soft' : ''} ${view === 'table' ? 'bg-accent-cobalt/15 text-accent-cobalt' : 'text-text-muted hover:bg-ink/5'}`}
                >
                  Table <span className="opacity-60">({rows.length.toLocaleString()})</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Body (collapsible) */}
        {!collapsed && (view === 'chart' && hasCharts && chartState ? (
          (() => {
            const res = processChartRecharts(rows, columns, chartState);
            return (
              <div>
                {suggestions.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto px-3 pt-3">
                    {suggestions.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => initFromSuggestion(messageId, suggestions, columns, i)}
                        className={`px-2 py-1 text-xs rounded border ${chartState.activeSuggestionIdx === i ? 'border-accent-cobalt text-accent-cobalt' : 'border-hairline-soft text-text-muted'}`}
                      >
                        {s.title ?? s.chart_type}
                      </button>
                    ))}
                  </div>
                )}
                <div className="p-3" style={{ height: 320 }}>
                  {res.ok ? (
                    <RechartsView processed={res.chart} state={chartState} />
                  ) : (
                    <div className="text-sm text-text-muted">{res.error}</div>
                  )}
                </div>
                {(chartState.subtitle || chartState.description) && (
                  <div className="px-3 pb-1 text-xs text-text-muted">
                    {chartState.subtitle || chartState.description}
                  </div>
                )}
                <div className="px-3 pb-2">
                  <button
                    onClick={() => setShowEdit((v) => !v)}
                    className="text-xs text-text-muted hover:text-ink"
                  >
                    {showEdit ? 'Hide' : 'Edit chart'}
                  </button>
                </div>
                {showEdit && (
                  <EditPanel
                    messageId={messageId}
                    columns={columns}
                    rows={rows}
                    onClose={() => setShowEdit(false)}
                  />
                )}
              </div>
            );
          })()
        ) : view === 'preview' && imageSrc ? (
          <div>
            <div className="p-3 flex justify-center">
              <img
                src={imageSrc}
                alt={message.data_title || 'Chart'}
                className="max-w-full rounded"
              />
            </div>
            {message.data_sql && <SqlDisclosure sql={message.data_sql} />}
          </div>
        ) : (
          <div className="overflow-auto max-h-80">
            {message.data_sql && (
              <SqlDisclosure sql={message.data_sql} />
            )}
            {rows.length === 0 ? (
              <div className="px-3 py-4 text-sm text-text-muted">No data.</div>
            ) : (
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="sticky top-0 bg-surface-soft z-10">
                    {columns.map((col) => (
                      <th
                        key={col.name}
                        className="px-3 py-2 text-left font-medium text-ink border-b border-hairline-soft whitespace-nowrap"
                      >
                        {col.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, TABLE_PAGE).map((row, i) => (
                    <tr key={i} className={i % 2 === 0 ? 'bg-transparent' : 'bg-ink/[0.03]'}>
                      {columns.map((col) => (
                        <td
                          key={col.name}
                          className="px-3 py-1.5 text-text-secondary border-b border-hairline-soft/60 whitespace-nowrap max-w-[200px] truncate"
                          title={String(row[col.name] ?? '')}
                        >
                          {row[col.name] == null ? <span className="opacity-30">—</span> : String(row[col.name])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {rows.length > TABLE_PAGE && (
              <div className="px-3 py-2 text-xs text-text-muted border-t border-hairline-soft/60">
                Showing first {TABLE_PAGE.toLocaleString()} of {rows.length.toLocaleString()} rows
              </div>
            )}
          </div>
        ))}
      </div>

    </div>
  );
}
