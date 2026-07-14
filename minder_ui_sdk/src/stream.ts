import { parseEnvelope, type EventEnvelope } from './events';

type Sub = (env: EventEnvelope) => void;

interface Shared {
  es: EventSource;
  subscribers: Set<Sub>;
  refCount: number;
}

const streams = new Map<string, Shared>();

/**
 * Subscribe to a connector SSE stream, sharing one `EventSource` per URL across
 * all callers. Envelopes are JSON-parsed and Zod-validated once; invalid frames
 * are dropped with a warning. The returned handle's `close()` decrements the
 * ref-count and closes the socket when the last subscriber leaves.
 */
export function getSharedStream(
  url: string,
  onEnvelope: Sub
): { close(): void } {
  let shared = streams.get(url);
  if (!shared) {
    const es = new EventSource(url);
    const s: Shared = { es, subscribers: new Set<Sub>(), refCount: 0 };
    es.onmessage = (e: MessageEvent) => {
      let data: unknown;
      try {
        data = JSON.parse(e.data);
      } catch {
        return;
      }
      const env = parseEnvelope(data);
      if (!env) {
        console.warn('[minder] dropped invalid event envelope');
        return;
      }
      s.subscribers.forEach((fn) => fn(env));
    };
    streams.set(url, s);
    shared = s;
  }
  shared.subscribers.add(onEnvelope);
  shared.refCount += 1;
  return {
    close() {
      const s = streams.get(url);
      if (!s) return;
      s.subscribers.delete(onEnvelope);
      s.refCount -= 1;
      if (s.refCount <= 0) {
        s.es.close();
        streams.delete(url);
      }
    },
  };
}

/** Test helper: force-close and forget every shared stream. */
export function __resetSharedStreams(): void {
  streams.forEach((s) => s.es.close());
  streams.clear();
}
