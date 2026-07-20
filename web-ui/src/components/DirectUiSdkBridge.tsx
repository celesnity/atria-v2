import { useEffect } from 'react';
import { wsClient } from '../api/websocket';
import { useChatStore } from '../stores/chat';

type UiRegistration = { module?: string; descriptors?: unknown[] };
type UiInvoke = { data?: { request_id?: string; session_id?: string; module?: string; action?: string; args?: unknown } };

/** Relays federated module UI capabilities through Minder's existing WebSocket. */
export function DirectUiSdkBridge() {
  useEffect(() => {
    const sendRegistration = (event: Event) => {
      const detail = (event as CustomEvent<UiRegistration>).detail;
      const sessionId = useChatStore.getState().currentSessionId;
      if (!sessionId || !detail?.module || !Array.isArray(detail.descriptors)) return;
      wsClient.send({ type: 'ui_sdk_register', data: { session_id: sessionId, module: detail.module, descriptors: detail.descriptors } });
    };
    const requestRegistration = () => window.dispatchEvent(new CustomEvent('minder:ui-sdk:request-register'));
    const offInvoke = wsClient.on('ui_sdk_invoke', (message) => {
      const detail = (message as UiInvoke).data;
      if (!detail?.request_id || detail.session_id !== useChatStore.getState().currentSessionId) return;
      window.dispatchEvent(new CustomEvent('minder:ui-sdk:invoke', { detail }));
    });
    const sendResult = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.request_id) wsClient.send({ type: 'ui_sdk_result', data: detail });
    };
    const unsubSession = useChatStore.subscribe((state, previous) => {
      if (state.currentSessionId && state.currentSessionId !== previous.currentSessionId) requestRegistration();
    });
    window.addEventListener('minder:ui-sdk:register', sendRegistration);
    window.addEventListener('minder:ui-sdk:result', sendResult);
    requestRegistration();
    return () => {
      window.removeEventListener('minder:ui-sdk:register', sendRegistration);
      window.removeEventListener('minder:ui-sdk:result', sendResult);
      offInvoke();
      unsubSession();
    };
  }, []);
  return null;
}
