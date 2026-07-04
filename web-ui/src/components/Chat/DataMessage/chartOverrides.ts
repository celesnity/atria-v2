// Load/save helpers for persisted chart overrides, keyed by chart_id per session.
//
// Loads are cached per session (one GET regardless of how many charts render).
// Saves are debounced per chart_id so dragging a color picker doesn't spam the
// backend. Failures are swallowed — persistence is best-effort and never blocks
// rendering (edits still live in the in-memory charts store).

import { apiClient } from '../../../api/client';
import type { ChartOverrides } from '../../../stores/charts';

const loadCache = new Map<string, Promise<Record<string, Partial<ChartOverrides>>>>();

/** Fetch (and cache) the whole overrides map for a session. */
export function loadSessionOverrides(
  sessionId: string
): Promise<Record<string, Partial<ChartOverrides>>> {
  let p = loadCache.get(sessionId);
  if (!p) {
    p = apiClient
      .getChartOverrides(sessionId)
      .then((m) => (m ?? {}) as Record<string, Partial<ChartOverrides>>)
      .catch(() => ({}));
    loadCache.set(sessionId, p);
  }
  return p;
}

/** Invalidate the cache (e.g. on session switch) so the next load re-fetches. */
export function clearOverridesCache(sessionId?: string) {
  if (sessionId) loadCache.delete(sessionId);
  else loadCache.clear();
}

const saveTimers = new Map<string, ReturnType<typeof setTimeout>>();

/** Debounced save of one chart's overrides (keyed by session+chart). */
export function saveChartOverridesDebounced(
  sessionId: string,
  chartId: string,
  overrides: ChartOverrides,
  delay = 800
) {
  const key = `${sessionId}:${chartId}`;
  const existing = saveTimers.get(key);
  if (existing) clearTimeout(existing);
  saveTimers.set(
    key,
    setTimeout(() => {
      saveTimers.delete(key);
      apiClient
        .saveChartOverrides(sessionId, chartId, overrides as Record<string, unknown>)
        .catch(() => { /* best-effort */ });
    }, delay)
  );
}
