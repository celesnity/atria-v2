import { QueryClient } from '@tanstack/react-query';
import { api } from '../api';

/** Shared React Query client for the produce module (bundled locally, not
 *  shared via Module Federation — it lives entirely inside this microfrontend). */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

/** queryFn helper bound to the module's REST fetch. */
export function detailQueryFn<T>(base: string, path: string) {
  return () => api<T>(base, path);
}
