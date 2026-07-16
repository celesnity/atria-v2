import { useQuery } from '@tanstack/react-query';
import { api } from '../api';

/**
 * Thin React Query wrapper over the module's `api()` fetch. Pass `enabled` to
 * fetch lazily — e.g. only when a detail modal is open:
 *
 *   useApiQuery(base, `/wip/stations/${id}/status`, { enabled: opened });
 */
export function useApiQuery<T>(
  base: string,
  path: string | null,
  opts: { enabled?: boolean } = {},
) {
  const enabled = (opts.enabled ?? true) && !!path;
  return useQuery<T>({
    queryKey: ['produce', base, path],
    queryFn: () => api<T>(base, path as string),
    enabled,
  });
}
