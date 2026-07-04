/**
 * Tools Settings — toggle individual agent tools on/off.
 *
 * Disabling a tool drops its schema from the LLM request on the next turn,
 * trimming context tokens. Changes persist to the global settings file and
 * apply immediately (no restart).
 */

import { useEffect, useMemo, useState } from 'react';
import { Search, AlertTriangle } from 'lucide-react';
import { listTools, updateDisabledTools, type ToolInfo } from '../../api/tools';

// Tools the agent generally needs to function — disabling is allowed (you asked
// for full control) but flagged so it isn't done by accident.
const CORE_TOOLS = new Set([
  'read_file',
  'edit_file',
  'write_file',
  'run_command',
  'batch_tool',
  'list_files',
  'search',
]);

export function ToolsSettings() {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setTools(await listTools());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load tools');
    } finally {
      setLoading(false);
    }
  };

  const persist = async (next: ToolInfo[]) => {
    setTools(next); // optimistic
    setSaving(true);
    setError(null);
    try {
      const disabled = next.filter(t => !t.enabled).map(t => t.name);
      const fresh = await updateDisabledTools(disabled);
      setTools(fresh);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
      await load(); // reconcile with server on failure
    } finally {
      setSaving(false);
    }
  };

  const toggle = (name: string) =>
    persist(tools.map(t => (t.name === name ? { ...t, enabled: !t.enabled } : t)));

  const setAll = (enabled: boolean) => persist(tools.map(t => ({ ...t, enabled })));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return tools;
    return tools.filter(
      t => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q),
    );
  }, [tools, query]);

  const grouped = useMemo(() => {
    const map = new Map<string, ToolInfo[]>();
    for (const t of filtered) {
      const arr = map.get(t.category) ?? [];
      arr.push(t);
      map.set(t.category, arr);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  const enabledCount = tools.filter(t => t.enabled).length;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div>
          <p className="text-sm font-medium text-ink">Agent Tools</p>
          <p className="text-xs text-text-muted mt-0.5">
            {enabledCount}/{tools.length} enabled · disabled tools are cut from the model context on
            the next turn
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAll(true)}
            disabled={saving || loading}
            className="px-2.5 py-1.5 text-xs rounded-md text-text-secondary hover:text-ink hover:bg-surface-soft transition-colors disabled:opacity-40 cursor-pointer"
          >
            Enable all
          </button>
          <button
            onClick={() => setAll(false)}
            disabled={saving || loading}
            className="px-2.5 py-1.5 text-xs rounded-md text-text-secondary hover:text-ink hover:bg-surface-soft transition-colors disabled:opacity-40 cursor-pointer"
          >
            Disable all
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="flex items-center gap-2 bg-surface-soft rounded-md px-2.5 py-1.5">
        <Search className="w-3.5 h-3.5 text-text-muted flex-shrink-0" />
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search tools…"
          className="flex-1 bg-transparent text-sm text-ink placeholder:text-text-muted outline-none min-w-0"
        />
      </div>

      {error && (
        <p className="text-xs text-semantic-danger font-mono bg-semantic-danger/10 rounded px-2 py-1.5">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-text-muted py-8 text-center">Loading tools…</p>
      ) : grouped.length === 0 ? (
        <p className="text-sm text-text-muted py-8 text-center">No tools match “{query}”.</p>
      ) : (
        <div className="space-y-5">
          {grouped.map(([category, items]) => (
            <div key={category}>
              <p className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-1.5">
                {category}
              </p>
              <div className="divide-y divide-hairline-soft rounded-md border border-hairline-soft">
                {items.map(tool => (
                  <div key={tool.name} className="flex items-start gap-3 px-3 py-2.5">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-mono text-ink truncate">{tool.name}</span>
                        {CORE_TOOLS.has(tool.name) && (
                          <span
                            title="Core tool — disabling may break the agent"
                            className="inline-flex items-center gap-0.5 text-[10px] text-amber-500"
                          >
                            <AlertTriangle className="w-3 h-3" /> core
                          </span>
                        )}
                      </div>
                      {tool.description && (
                        <p className="text-xs text-text-muted mt-0.5 line-clamp-2">
                          {tool.description}
                        </p>
                      )}
                    </div>
                    <Switch
                      checked={tool.enabled}
                      disabled={saving}
                      onChange={() => toggle(tool.name)}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Switch({
  checked,
  disabled,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-[50%] transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
        checked ? 'bg-accent-main-100' : 'bg-text-muted/40'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-[50%] bg-white shadow transition-transform ${
          checked ? 'translate-x-4' : 'translate-x-0.5'
        }`}
      />
    </button>
  );
}
