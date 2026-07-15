import { useEffect, useRef, useState } from 'react';
import { getSharedStream } from './stream';
import { UI_INTENT, type EventEnvelope, type EventActor } from './events';

/**
 * The agent-facing sensing surface, mirrored from the module SDK's event
 * envelope + `/connector/context`. These types are the UI half of "B. sense
 * state" and "A. discovery": a normalized event a panel can react to live, and
 * the caller's autonomy/scope so the UI can show what the agent may do here.
 */

// Envelope types live in `./events` (single source of truth); re-export so
// existing consumers importing them from here keep working.
export type { EventEnvelope, EventActor };

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
  /** Session whose stream to join; shares the driver's EventSource when equal. */
  sessionId?: string;
  /** SSE path relative to `apiBase`. Defaults to `/connector/stream`. */
  path?: string;
  /** Keep only the last N events (ring buffer). Defaults to 100. */
  limit?: number;
  /** Only surface these event types (matches `EventEnvelope.type`). */
  types?: string[];
  /** Called for every accepted envelope, in addition to buffering. */
  onEvent?: (env: EventEnvelope) => void;
}

/**
 * Subscribe to a module's normalized event stream (the merged
 * `/connector/stream`) and return the most recent envelopes. `ui.intent` events
 * are excluded — the agent driver owns those. Pass `types` to filter further,
 * and `sessionId` to share the driver's single EventSource.
 *
 *   const { events } = useModuleEvents(apiBase, { sessionId, types: ['queue.changed'] });
 */
export function useModuleEvents(
  apiBase: string,
  opts: UseModuleEventsOptions = {},
): { events: EventEnvelope[]; connected: boolean } {
  const { sessionId, path = '/connector/stream', limit = 100, types, onEvent } = opts;
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const typeKey = types ? types.join(',') : '';
  useEffect(() => {
    if (!apiBase || typeof EventSource === 'undefined') return;
    const qs = sessionId ? `?session=${encodeURIComponent(sessionId)}` : '';
    const url = `${apiBase.replace(/\/$/, '')}${path}${qs}`;
    const handle = getSharedStream(url, (env) => {
      if (env.type === UI_INTENT) return; // the driver owns intents
      if (types && !types.includes(env.type)) return;
      onEventRef.current?.(env);
      setEvents((prev) => {
        const next = [...prev, env];
        return next.length > limit ? next.slice(next.length - limit) : next;
      });
    });
    return () => handle.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase, path, limit, typeKey, sessionId]);

  // The shared EventSource auto-reconnects; a per-consumer connected flag is no
  // longer meaningful, so report connected once mounted.
  return { events, connected: true };
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
