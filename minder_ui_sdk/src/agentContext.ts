import { useEffect, useRef, useState } from 'react';

/**
 * The agent-facing sensing surface, mirrored from the module SDK's event
 * envelope + `/connector/context`. These types are the UI half of "B. sense
 * state" and "A. discovery": a normalized event a panel can react to live, and
 * the caller's autonomy/scope so the UI can show what the agent may do here.
 */

/** Who acted — distinguishes an agent acting on a user's behalf from a human. */
export interface EventActor {
  kind: 'agent' | 'human' | 'system';
  agent_id?: string | null;
  on_behalf_of?: string | null;
}

/** A normalized, timestamped, sourced record of something that happened. */
export interface EventEnvelope<P = unknown> {
  event_id: string;
  type: string;
  module: string;
  ts: string;
  source: string;
  actor?: EventActor | null;
  session_id?: string | null;
  payload: P;
}

/** The caller's autonomy + identity + per-action permission, from `/context`. */
export interface AgentContext {
  module: string;
  autonomy: string;
  principal: {
    username: string;
    authenticated: boolean;
    roles: string[];
    scopes: string[];
  };
  actions: { name: string; risk: string; read_only: boolean; allowed: boolean }[];
}

export interface UseModuleEventsOptions {
  /** SSE path relative to `apiBase`. Defaults to `/connector/events`. */
  path?: string;
  /** Keep only the last N events (ring buffer). Defaults to 100. */
  limit?: number;
  /** Only surface these event types (matches `EventEnvelope.type`). */
  types?: string[];
  /** Called for every accepted envelope, in addition to buffering. */
  onEvent?: (env: EventEnvelope) => void;
}

/**
 * Subscribe to a module's normalized event stream over SSE and return the most
 * recent envelopes plus a live `connected` flag. Reconnects are handled by the
 * browser's `EventSource`. Pass `types` to filter.
 *
 *   const { events, connected } = useModuleEvents(apiBase, { types: ['queue.changed'] });
 */
export function useModuleEvents(
  apiBase: string,
  opts: UseModuleEventsOptions = {},
): { events: EventEnvelope[]; connected: boolean } {
  const { path = '/connector/events', limit = 100, types, onEvent } = opts;
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const typeKey = types ? types.join(',') : '';
  useEffect(() => {
    if (!apiBase || typeof EventSource === 'undefined') return;
    const url = `${apiBase.replace(/\/$/, '')}${path}`;
    const es = new EventSource(url);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (e: MessageEvent) => {
      let env: EventEnvelope;
      try {
        env = JSON.parse(e.data) as EventEnvelope;
      } catch {
        return;
      }
      if (types && !types.includes(env.type)) return;
      onEventRef.current?.(env);
      setEvents((prev) => {
        const next = [...prev, env];
        return next.length > limit ? next.slice(next.length - limit) : next;
      });
    };
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, path, limit, typeKey]);

  return { events, connected };
}

/**
 * Fetch the agent's context for this module (autonomy level, principal scope,
 * per-action allowance). One-shot on mount / when `apiBase` changes.
 */
export function useAgentContext(
  apiBase: string,
  headers?: Record<string, string>,
): { context: AgentContext | null; loading: boolean; error: string | null } {
  const [context, setContext] = useState<AgentContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const headerKey = headers ? JSON.stringify(headers) : '';

  useEffect(() => {
    if (!apiBase) return;
    let alive = true;
    setLoading(true);
    fetch(`${apiBase.replace(/\/$/, '')}/connector/context`, { headers })
      .then((r) => {
        if (!r.ok) throw new Error(`context ${r.status}`);
        return r.json();
      })
      .then((data: AgentContext) => {
        if (alive) {
          setContext(data);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, headerKey]);

  return { context, loading, error };
}
