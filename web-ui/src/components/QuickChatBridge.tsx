import { useEffect } from 'react';
import { useChatStore } from '../stores/chat';

/**
 * QuickChatBridge — routes a module's mascot "quick chat" to the real Minder
 * agent. A federated module (the mascot lives in module_template) can't reach
 * the host's chat store, so it fires a `minder:quickchat:send` window event;
 * this bridge forwards the text through `useChatStore.sendMessage` (same path
 * as the main composer) and streams the assistant's answer back as
 * `minder:quickchat:reply` events tagged with the request id.
 *
 * Event contract mirrors `minder_ui_sdk/src/quickChat.ts` — kept inline here so
 * the host doesn't need to depend on the module SDK just for two string keys.
 */

const SEND = 'minder:quickchat:send';
const REPLY = 'minder:quickchat:reply';

type Phase = 'thinking' | 'streaming' | 'done' | 'error';

function reply(id: string, phase: Phase, text?: string) {
  window.dispatchEvent(new CustomEvent(REPLY, { detail: { id, phase, text } }));
}

export function QuickChatBridge() {
  useEffect(() => {
    // The request currently being answered, and where its assistant turn starts
    // in the message list (so we never mistake the previous turn for the reply).
    let activeId: string | null = null;
    let baseLen = 0;
    let sawText = false;
    let safety: ReturnType<typeof setTimeout> | undefined;

    const finish = (phase: Phase, text?: string) => {
      if (!activeId) return;
      reply(activeId, phase, text);
      activeId = null;
      sawText = false;
      clearTimeout(safety);
    };

    const onSend = (e: Event) => {
      const detail = (e as CustomEvent).detail as { id?: string; text?: string } | undefined;
      const id = detail?.id;
      const text = (detail?.text ?? '').trim();
      if (!id || !text) return;

      const store = useChatStore.getState();
      if (!store.currentSessionId) {
        reply(id, 'error', 'Chưa có phiên chat — mở một cuộc trò chuyện trước nhé.');
        return;
      }

      activeId = id;
      sawText = false;
      reply(id, 'thinking');
      // sendMessage synchronously appends the user message, so snapshot the
      // length right after: the assistant reply is the first assistant message
      // at index >= baseLen.
      void store.sendMessage(text);
      const ss = useChatStore.getState().sessionStates[store.currentSessionId];
      baseLen = ss ? ss.messages.length : 0;

      clearTimeout(safety);
      safety = setTimeout(() => finish(sawText ? 'done' : 'error', sawText ? undefined : 'Hết thời gian chờ.'), 90_000);
    };

    const unsub = useChatStore.subscribe((state) => {
      if (!activeId) return;
      const sid = state.currentSessionId;
      const ss = sid ? state.sessionStates[sid] : undefined;
      if (!ss) return;

      // First assistant message produced after we sent → this turn's answer.
      let answer: string | undefined;
      for (let i = Math.max(0, baseLen); i < ss.messages.length; i++) {
        if (ss.messages[i].role === 'assistant') {
          answer = ss.messages[i].content;
          break;
        }
      }
      const content = (answer ?? '').trim();
      if (content) {
        sawText = true;
        reply(activeId, 'streaming', content);
      }
      // Turn finished (loading cleared) and we have text → done.
      if (!ss.isLoading && sawText) {
        finish('done', content);
      }
    });

    window.addEventListener(SEND, onSend);
    return () => {
      window.removeEventListener(SEND, onSend);
      unsub();
      clearTimeout(safety);
    };
  }, []);

  return null;
}
