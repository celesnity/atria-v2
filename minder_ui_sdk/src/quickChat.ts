import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Quick-chat bridge — lets a federated module (e.g. the mascot) ask the host's
 * real Minder agent a question without importing any host code. The two sides
 * only agree on two `window` CustomEvents, so the module bundle and the host
 * bundle stay fully decoupled:
 *
 *   module → host   `minder:quickchat:send`   { id, text }
 *   host   → module `minder:quickchat:reply`  { id, phase, text? }
 *
 * The host mounts a bridge that listens for `send`, forwards the text to its
 * chat store / websocket, and streams the assistant's answer back as `reply`
 * events tagged with the same `id`. The module consumes replies with
 * `useQuickChat()`.
 */

export const QUICK_CHAT_SEND = 'minder:quickchat:send';
export const QUICK_CHAT_REPLY = 'minder:quickchat:reply';

/** Lifecycle of one quick-chat request, from ask to answer. */
export type QuickChatPhase = 'idle' | 'thinking' | 'streaming' | 'done' | 'error';

export interface QuickChatSendDetail {
  id: string;
  text: string;
}

export interface QuickChatReplyDetail {
  id: string;
  phase: QuickChatPhase;
  /** Assistant text so far (streaming) / final (done) / message (error). */
  text?: string;
}

/** Emit a reply for a request `id` — used by the HOST bridge. */
export function emitQuickChatReply(detail: QuickChatReplyDetail): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent<QuickChatReplyDetail>(QUICK_CHAT_REPLY, { detail }));
}

function newRequestId(): string {
  // Module runtime — Date.now()/Math.random() are available here (unlike in
  // workflow scripts). Uniqueness only needs to hold within one browser tab.
  return `qc_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export interface UseQuickChatResult {
  /** Current phase of the in-flight (or last) request. */
  phase: QuickChatPhase;
  /** Latest assistant text for the active request (empty until it streams). */
  text: string;
  /** True between `ask()` and the terminal `done`/`error` phase. */
  pending: boolean;
  /** Send a question to the host agent. Returns the request id. */
  ask: (text: string) => string;
  /** Reset back to idle (e.g. after showing the answer). */
  reset: () => void;
}

/**
 * Ask the host agent a question and follow its answer live. Only replies whose
 * `id` matches the most recent `ask()` are surfaced, so stale answers from an
 * earlier question can't bleed into a newer one.
 */
export function useQuickChat(): UseQuickChatResult {
  const [phase, setPhase] = useState<QuickChatPhase>('idle');
  const [text, setText] = useState('');
  const activeId = useRef<string | null>(null);

  useEffect(() => {
    const onReply = (e: Event) => {
      const d = (e as CustomEvent<QuickChatReplyDetail>).detail;
      if (!d || d.id !== activeId.current) return;
      setPhase(d.phase);
      if (typeof d.text === 'string') setText(d.text);
    };
    window.addEventListener(QUICK_CHAT_REPLY, onReply);
    return () => window.removeEventListener(QUICK_CHAT_REPLY, onReply);
  }, []);

  const ask = useCallback((question: string) => {
    const id = newRequestId();
    activeId.current = id;
    setPhase('thinking');
    setText('');
    if (typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent<QuickChatSendDetail>(QUICK_CHAT_SEND, { detail: { id, text: question } }),
      );
    }
    return id;
  }, []);

  const reset = useCallback(() => {
    activeId.current = null;
    setPhase('idle');
    setText('');
  }, []);

  return { phase, text, pending: phase === 'thinking' || phase === 'streaming', ask, reset };
}
