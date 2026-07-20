import { useEffect } from 'react';
import { wsClient } from '../api/websocket';

type ToolEvent = { data?: { tool_call_id?: string; tool_name?: string; arguments?: unknown } };

/** Forward Minder's native chat tool lifecycle to Embinder's visual cursor. */
export function EmbinderCursorBridge() {
  useEffect(() => {
    const phase = (detail: object) =>
      window.dispatchEvent(new CustomEvent('minder:embinder-phase', { detail }));
    const offCall = wsClient.on('tool_call', (message) => {
      const event = message as ToolEvent;
      if (!event.data?.tool_name) return;
      phase({ type: 'intent', id: event.data.tool_call_id, name: event.data.tool_name, argsPreview: event.data.arguments });
    });
    const offResult = wsClient.on('tool_result', (message) => {
      const event = message as ToolEvent;
      phase({ type: 'done', id: event.data?.tool_call_id });
    });
    return () => { offCall(); offResult(); };
  }, []);
  return null;
}
