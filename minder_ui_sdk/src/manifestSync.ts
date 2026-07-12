import { transformSync } from 'esbuild';
import type { TabMeta } from './types';

/** Strip → {id,label} and drop everything else (icon/component never ship). */
function toWire(tabs: TabMeta[]): Array<{ id: string; label: string }> {
  return tabs.map((t) => ({ id: String(t.id), label: String(t.label) }));
}

/**
 * Evaluate a plain-data tabs module (`export const TABS = [...]`, no React
 * imports) and return the declared tabs. Uses esbuild to strip TS syntax, then
 * runs the emitted CJS in a bare function scope — safe because the module is
 * data only.
 */
export function extractTabsFromSource(tsSource: string): TabMeta[] {
  const { code } = transformSync(tsSource, { loader: 'ts', format: 'cjs' });
  const mod = { exports: {} as Record<string, unknown> };
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  new Function('module', 'exports', code)(mod, mod.exports);
  const tabs = (mod.exports.TABS ?? mod.exports.default) as unknown;
  if (!Array.isArray(tabs)) {
    throw new Error('tabs source must `export const TABS: TabMeta[]`');
  }
  // Strip to the wire shape ({id,label}) — icon/other fields never reach the host.
  return toWire(tabs as TabMeta[]);
}

/** Merge tabs into `dashboard.tabs`, preserving all other manifest fields. */
export function applyTabsToManifest(manifestRaw: string, tabs: TabMeta[]): string {
  const manifest = JSON.parse(manifestRaw) as Record<string, unknown>;
  const dashboard = (manifest.dashboard ?? {}) as Record<string, unknown>;
  dashboard.tabs = toWire(tabs);
  manifest.dashboard = dashboard;
  return JSON.stringify(manifest, null, 2) + '\n';
}

/** True when the manifest's dashboard.tabs already equals `tabs` (id+label). */
export function manifestTabsMatch(manifestRaw: string, tabs: TabMeta[]): boolean {
  try {
    const cur = ((JSON.parse(manifestRaw) as any)?.dashboard?.tabs ?? []) as TabMeta[];
    return JSON.stringify(toWire(cur)) === JSON.stringify(toWire(tabs));
  } catch {
    return false;
  }
}
