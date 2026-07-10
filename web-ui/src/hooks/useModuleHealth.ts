import { useEffect, useState } from 'react';
import { ModulesApi } from '../api/modules';
import { useModulesStore } from '../stores/modules';

export type HealthStatus = 'loading' | 'ok' | 'down';

const POLL_MS = 30_000;

/**
 * Poll `GET /api/modules/{name}/health` for every service module (those with a
 * `manifest.remote`, i.e. `summary.remote === true`) and return a `name → status`
 * map. Polls on mount and every ~30s. Non-service modules are omitted from the map
 * (no dot); an unreachable connector or non-ok response maps to `'down'`.
 *
 * The endpoint never throws, so this quietly reflects state without spamming errors.
 */
export function useModuleHealth(): Record<string, HealthStatus> {
  const modules = useModulesStore((s) => s.modulesWithDashboards);
  // Poll only service modules — those are the ones with a connector to probe.
  const serviceNames = modules.filter((m) => m.remote).map((m) => m.name);
  const key = serviceNames.join(',');

  const [health, setHealth] = useState<Record<string, HealthStatus>>({});

  useEffect(() => {
    if (serviceNames.length === 0) {
      setHealth({});
      return;
    }
    let cancelled = false;

    // Seed unknowns as loading (keep known statuses to avoid a flash on re-poll).
    setHealth((prev) => {
      const next: Record<string, HealthStatus> = {};
      for (const n of serviceNames) next[n] = prev[n] ?? 'loading';
      return next;
    });

    const poll = async () => {
      const results = await Promise.all(
        serviceNames.map(async (n) => [n, (await ModulesApi.health(n)).ok] as const),
      );
      if (cancelled) return;
      setHealth((prev) => {
        const next = { ...prev };
        for (const [n, ok] of results) next[n] = ok ? 'ok' : 'down';
        return next;
      });
    };

    poll();
    const id = window.setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return health;
}
