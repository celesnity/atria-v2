import { useCallback, useEffect, useState } from 'react';

/** JSON fetch against Track A REST. Throws Error(detail) on non-2xx. */
export async function api<T = unknown>(base: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Read hook: fetches on mount and whenever `deps` change; exposes reload(). */
export function useApi<T = unknown>(base: string, path: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    api<T>(base, path)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(String(e.message ?? e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base, path, ...deps]);

  useEffect(() => { reload(); }, [reload]);
  return { data, loading, reload, error };
}
