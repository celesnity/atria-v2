import { useMemo, useState, useCallback } from 'react';
import { Lock, X, Plus } from 'lucide-react';
import type { DataColumn } from '../../../types';
import { apiClient } from '../../../api/client';
import { useChatStore } from '../../../stores/chat';

const MAX_EDIT_ROWS = 2000;

interface Props {
  messageId: string;
  title: string;
  columns: DataColumn[];
  rows: Record<string, any>[];
  source: { module?: string; file: string; session?: string };
  warning?: string;
}

/**
 * Inline editable grid bound to a module CSV dataset. Edits live in local state
 * and are persisted to the module via PUT /api/modules/{module}/data/write on
 * Save. Everything is defensive: a failed save keeps the user's edits and shows
 * an inline error rather than crashing the chat.
 */
export function EditableDataTable({ messageId, title, columns, rows, source, warning }: Props) {
  const updateDataMessageRows = useChatStore((s) => s.updateDataMessageRows);
  // Stable column list; fall back to keys of the first row if columns are absent.
  const cols: DataColumn[] = useMemo(() => {
    if (columns && columns.length) return columns;
    const first = rows && rows[0];
    if (first && typeof first === 'object') {
      return Object.keys(first).map((name) => ({ name, type: 'string' as const }));
    }
    return [];
  }, [columns, rows]);

  const [editRows, setEditRows] = useState<Record<string, any>[]>(() =>
    (rows || []).map((r) => ({ ...r })),
  );
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const overflow = editRows.length > MAX_EDIT_ROWS;
  const visibleRows = overflow ? editRows.slice(0, MAX_EDIT_ROWS) : editRows;

  const setCell = useCallback((rowIdx: number, colName: string, value: string) => {
    setEditRows((prev) => {
      const next = prev.slice();
      next[rowIdx] = { ...next[rowIdx], [colName]: value };
      return next;
    });
    setDirty(true);
    setNote(null);
  }, []);

  const addRow = useCallback(() => {
    setEditRows((prev) => {
      const blank: Record<string, any> = {};
      for (const c of cols) blank[c.name] = '';
      return [...prev, blank];
    });
    setDirty(true);
    setNote(null);
  }, [cols]);

  const deleteRow = useCallback((rowIdx: number) => {
    setEditRows((prev) => prev.filter((_, i) => i !== rowIdx));
    setDirty(true);
    setNote(null);
  }, []);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    setNote(null);
    try {
      const res = source.session
        ? await apiClient.writeSessionDataset(source.session, source.file, cols, editRows)
        : await apiClient.writeDataset(source.module as string, source.file, cols, editRows);
      setDirty(false);
      setNote(`Saved ${res?.rows ?? editRows.length} rows to ${source.file}`);
      // Keep the stored snapshot in sync so leaving the chat (e.g. to view the
      // module dashboard) and coming back doesn't revert to the pre-edit values.
      updateDataMessageRows(messageId, cols, editRows.map((r) => ({ ...r })));
    } catch (e: any) {
      setError(e?.message ? String(e.message) : 'Failed to save');
    } finally {
      setSaving(false);
    }
  }, [cols, editRows, source.module, source.session, source.file, messageId, updateDataMessageRows]);

  const reload = useCallback(async () => {
    setSaving(true);
    setError(null);
    setNote(null);
    try {
      const data = source.session
        ? await apiClient.readSessionDataset(source.session, source.file)
        : await apiClient.readDataset(source.module as string, source.file);
      const fresh = (data?.rows || []).map((r) => ({ ...r }));
      setEditRows(fresh);
      setDirty(false);
      setNote('Reloaded from source');
      updateDataMessageRows(messageId, cols, fresh);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : 'Failed to reload');
    } finally {
      setSaving(false);
    }
  }, [source.module, source.session, source.file, messageId, cols, updateDataMessageRows]);

  return (
    <div className="my-3 relative">
      <div className="rounded-lg border border-hairline-soft bg-surface-soft overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-hairline-soft">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-sm font-semibold text-ink truncate">{title || 'Data'}</span>
            <span className="text-[11px] px-1.5 py-0.5 rounded bg-accent-cobalt/10 text-accent-cobalt border border-accent-cobalt/20">
              editable
            </span>
            {warning && (
              <span
                className="text-[11px] px-1.5 py-0.5 rounded bg-accent-cobalt/10 text-accent-cobalt border border-accent-cobalt/20"
                title={warning}
              >
                {warning}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={addRow}
              disabled={saving}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border border-hairline-soft text-text-secondary hover:bg-ink/5 hover:text-ink transition-colors duration-fast disabled:opacity-50 cursor-pointer"
            >
              <Plus className="w-3 h-3" strokeWidth={2} aria-hidden="true" /> Row
            </button>
            <button
              onClick={reload}
              disabled={saving}
              className="px-2 py-1 text-xs rounded border border-hairline-soft text-text-muted hover:bg-ink/5 disabled:opacity-50"
              title="Discard changes and reload from the saved file"
            >
              Reload
            </button>
            <button
              onClick={save}
              disabled={saving || !dirty}
              className="px-2.5 py-1 text-xs rounded bg-accent-cobalt text-canvas hover:bg-accent-cobalt/90 disabled:opacity-40"
            >
              {saving ? 'Saving…' : dirty ? 'Save' : 'Saved'}
            </button>
          </div>
        </div>

        {error && (
          <div className="px-3 py-2 text-xs text-semantic-danger bg-semantic-danger/10 border-b border-semantic-danger/20">
            {error}
          </div>
        )}
        {note && !error && (
          <div className="px-3 py-2 text-xs text-semantic-success bg-semantic-success/10 border-b border-semantic-success/20">
            {note}
          </div>
        )}

        {/* Body */}
        <div className="overflow-auto max-h-96">
          {cols.length === 0 ? (
            <div className="px-3 py-4 text-sm text-text-muted">No columns.</div>
          ) : (
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="sticky top-0 bg-surface-soft z-10">
                  {cols.map((col) => (
                    <th
                      key={col.name}
                      className="px-2 py-2 text-left font-medium text-ink border-b border-hairline-soft whitespace-nowrap"
                    >
                      {col.name}
                      {col.editable === false && (
                        <Lock
                          className="inline-block ml-1 w-3 h-3 align-[-1px] text-text-muted"
                          strokeWidth={2}
                          aria-label="read-only"
                        />
                      )}
                    </th>
                  ))}
                  <th className="px-2 py-2 border-b border-hairline-soft w-8" />
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row, ri) => (
                  <tr key={ri} className={ri % 2 === 0 ? 'bg-transparent' : 'bg-ink/[0.03]'}>
                    {cols.map((col) => {
                      const readOnly = col.editable === false;
                      const value = row[col.name];
                      return (
                        <td
                          key={col.name}
                          className="px-1 py-0.5 border-b border-hairline-soft/60 align-middle"
                        >
                          {readOnly ? (
                            <span className="px-1 text-text-muted whitespace-nowrap">
                              {value == null ? '' : String(value)}
                            </span>
                          ) : (
                            <input
                              value={value == null ? '' : String(value)}
                              onChange={(e) => setCell(ri, col.name, e.target.value)}
                              inputMode={col.type === 'number' ? 'decimal' : undefined}
                              className="w-full min-w-[80px] bg-transparent text-ink px-1 py-1 rounded border border-transparent hover:border-hairline focus:border-accent-cobalt/50 focus:bg-canvas outline-none"
                            />
                          )}
                        </td>
                      );
                    })}
                    <td className="px-1 py-0.5 border-b border-hairline-soft/60 text-center">
                      <button
                        onClick={() => deleteRow(ri)}
                        disabled={saving}
                        title="Delete row"
                        aria-label="Delete row"
                        className="inline-flex items-center text-text-muted hover:text-semantic-danger disabled:opacity-50 px-1 cursor-pointer transition-colors duration-fast"
                      >
                        <X className="w-3.5 h-3.5" strokeWidth={2} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="flex items-center justify-between px-3 py-1.5 text-[11px] text-text-muted border-t border-hairline-soft/60">
          <span>
            {editRows.length.toLocaleString()} row{editRows.length === 1 ? '' : 's'}
            {overflow && ` · editing first ${MAX_EDIT_ROWS.toLocaleString()}`}
          </span>
          <span className="opacity-60 truncate">
            {(source.session ? `session:${source.session}` : source.module)}/{source.file}
          </span>
        </div>
      </div>
    </div>
  );
}
