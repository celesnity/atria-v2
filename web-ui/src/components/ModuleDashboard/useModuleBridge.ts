import { useEffect, useRef } from 'react';
import { wsClient } from '../../api/websocket';
import { apiClient } from '../../api/client';
import { useModulesStore, type BadgeSeverity } from '../../stores/modules';
import { useToastStore, type ToastVariant } from '../../stores/toast';
import type { WSMessage } from '../../types';
import {
  publishModuleEmbinderContext,
  registerModuleEmbinderSurface,
} from './embinderModuleBridge';

interface UseModuleBridgeArgs {
  moduleName: string;
  sessionId: string | null;
  iframeRef: React.RefObject<HTMLIFrameElement>;
  visible: boolean;
}

type InboundMessage =
  | { type: 'ready' }
  | { type: 'badge'; value: { count: number; severity: BadgeSeverity } | null }
  | { type: 'title'; text: string }
  | { type: 'toast'; message: string; severity?: ToastVariant }
  | {
      type: 'openBlock';
      block: string;
      props?: Record<string, unknown>;
    }
  | { type: 'openChat' }
  | { type: 'openHistory'; sessionId: string; projectId?: number | null }
  | { type: 'embinder:context'; context: Record<string, unknown> }
  | {
      type: 'embinder:result';
      requestId: string;
      result?: unknown;
      error?: string;
    }
  | {
      type: 'run';
      requestId: string;
      script: string;
      args?: string[];
      stdin?: string;
      timeout_ms?: number;
    };

const SEVERITY_TO_TOAST: Record<string, ToastVariant> = {
  info: 'info',
  success: 'success',
  warning: 'warning',
  danger: 'error',
  error: 'error',
};

/**
 * Bridge between the host React app and a module iframe.
 *
 * Listens for postMessage events from the iframe and proxies them to
 * stores / REST endpoints. Forwards lifecycle (`context`, `visibility`)
 * and module file change notifications (`change`) into the iframe.
 */
export function useModuleBridge({
  moduleName,
  sessionId,
  iframeRef,
  visible,
}: UseModuleBridgeArgs) {
  const readyRef = useRef(false);
  const readyWaitersRef = useRef(new Set<{ resolve: () => void; reject: (error: Error) => void; timer: number }>());
  const embinderCallsRef = useRef(
    new Map<string, { resolve: (result: unknown) => void; reject: (error: Error) => void; timer: number }>(),
  );
  // Stash latest values in refs so the message handler stays referentially stable.
  const sessionIdRef = useRef(sessionId);
  const visibleRef = useRef(visible);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    visibleRef.current = visible;
  }, [visible]);

  // postMessage helper that targets the module iframe.
  const postToIframe = (msg: unknown) => {
    const win = iframeRef.current?.contentWindow;
    if (!win) return;
    // The iframe is loaded from a same-origin /api/modules/... endpoint, so '*' is
    // acceptable here; tighten if cross-origin hosting is introduced.
    win.postMessage(msg, '*');
  };

  useEffect(() => {
    const unregister = registerModuleEmbinderSurface(moduleName, async (action, args) => {
      if (!readyRef.current) {
        await new Promise<void>((resolve, reject) => {
          const waiter = {
            resolve: () => {
              window.clearTimeout(waiter.timer);
              readyWaitersRef.current.delete(waiter);
              resolve();
            },
            reject: (error: Error) => {
              window.clearTimeout(waiter.timer);
              readyWaitersRef.current.delete(waiter);
              reject(error);
            },
            timer: 0,
          };
          waiter.timer = window.setTimeout(
            () => waiter.reject(new Error(`${moduleName} did not become ready for agent actions.`)),
            10_000,
          );
          readyWaitersRef.current.add(waiter);
        });
      }
      const win = iframeRef.current?.contentWindow;
      if (!win) throw new Error(`${moduleName} is not available for agent actions.`);
      const requestId = crypto.randomUUID();
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          embinderCallsRef.current.delete(requestId);
          reject(new Error(`${moduleName} did not respond to ${action}.`));
        }, 15_000);
        embinderCallsRef.current.set(requestId, { resolve, reject, timer });
        win.postMessage({ type: 'embinder:call', requestId, action, args }, '*');
      });
    });

    return () => {
      unregister();
      for (const waiter of readyWaitersRef.current) {
        waiter.reject(new Error(`${moduleName} closed before it became ready.`));
      }
      readyWaitersRef.current.clear();
      for (const pending of embinderCallsRef.current.values()) {
        window.clearTimeout(pending.timer);
        pending.reject(new Error(`${moduleName} closed before the agent action completed.`));
      }
      embinderCallsRef.current.clear();
    };
  }, [iframeRef, moduleName]);

  // Listen for messages from the iframe.
  useEffect(() => {
    const handler = async (event: MessageEvent) => {
      const win = iframeRef.current?.contentWindow;
      if (!win || event.source !== win) return;

      const msg = event.data as InboundMessage | undefined;
      if (!msg || typeof msg !== 'object' || !('type' in msg)) return;

      switch (msg.type) {
        case 'ready': {
          readyRef.current = true;
          for (const waiter of readyWaitersRef.current) waiter.resolve();
          postToIframe({
            type: 'context',
            sessionId: sessionIdRef.current,
            module: moduleName,
          });
          postToIframe({ type: 'visibility', visible: visibleRef.current });
          break;
        }
        case 'embinder:context': {
          publishModuleEmbinderContext(moduleName, msg.context);
          break;
        }
        case 'embinder:result': {
          const pending = embinderCallsRef.current.get(msg.requestId);
          if (!pending) break;
          embinderCallsRef.current.delete(msg.requestId);
          window.clearTimeout(pending.timer);
          if (msg.error) pending.reject(new Error(msg.error));
          else pending.resolve(msg.result);
          break;
        }
        case 'badge': {
          useModulesStore.getState().setBadge(moduleName, msg.value ?? null);
          break;
        }
        case 'title': {
          window.dispatchEvent(
            new CustomEvent('minder:module:title', {
              detail: { module: moduleName, text: msg.text },
            }),
          );
          break;
        }
        case 'toast': {
          const variant = SEVERITY_TO_TOAST[msg.severity ?? 'info'] ?? 'info';
          useToastStore.getState().addToast(msg.message, variant);
          break;
        }
        case 'openBlock': {
          try {
            await apiClient.pushBlock(
              sessionIdRef.current,
              moduleName,
              msg.block,
              msg.props ?? {},
            );
            useModulesStore.getState().closeDashboard();
          } catch (err) {
            console.error('[module bridge] openBlock failed', err);
            useToastStore.getState().addToast(
              err instanceof Error ? err.message : 'Failed to open block',
              'error',
            );
          }
          break;
        }
        case 'openChat': {
          useModulesStore.getState().closeDashboard();
          break;
        }
        case 'openHistory': {
          // Surface a chat the widget just saved: refresh the history sidebar
          // (so a new project like "Warehouse" appears), open the conversation
          // in the main view, then close the dashboard.
          try {
            const { useProjectsStore } = await import('../../stores/projects');
            const { useChatStore } = await import('../../stores/chat');
            await useProjectsStore.getState().loadProjects();
            if (msg.sessionId) {
              await useChatStore.getState().loadSession(String(msg.sessionId));
            }
          } catch (err) {
            console.error('[module bridge] openHistory failed', err);
          }
          useModulesStore.getState().closeDashboard();
          break;
        }
        case 'run': {
          const { requestId, script, args, stdin, timeout_ms } = msg;
          try {
            const result = await apiClient.runModuleScript(moduleName, {
              script,
              args: args ?? [],
              stdin,
              timeout_ms,
            });
            if (!result.ok) {
              postToIframe({
                type: 'run:error',
                requestId,
                kind: `http_${result.status}`,
                message: result.message,
              });
              break;
            }
            const data = result.data;
            postToIframe({
              type: 'run:result',
              requestId,
              exit_code: data.exit_code,
              stdout: data.stdout,
              stderr: data.stderr,
              duration_ms: data.duration_ms,
            });
          } catch (err) {
            postToIframe({
              type: 'run:error',
              requestId,
              kind: 'network',
              message: err instanceof Error ? err.message : String(err),
            });
          }
          break;
        }
        default:
          break;
      }
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
    // moduleName + iframeRef are stable for the component's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleName]);

  // Re-post context whenever sessionId changes (if iframe is ready).
  useEffect(() => {
    if (!readyRef.current) return;
    postToIframe({ type: 'context', sessionId, module: moduleName });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, moduleName]);

  // Re-post visibility whenever it flips.
  useEffect(() => {
    if (!readyRef.current) return;
    postToIframe({ type: 'visibility', visible });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // Forward WS modules.changed events as 'change' messages to the iframe.
  useEffect(() => {
    const unsubscribe = wsClient.on('modules.changed', (payload: WSMessage) => {
      const data = (payload as { data?: { module?: string; paths?: string[] } }).data ?? {};
      const changed = data.module;
      if (changed && changed !== '*' && changed !== moduleName) return;
      postToIframe({ type: 'change', paths: data.paths ?? [] });
    });
    return () => {
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleName]);

  // Forward WS artifact.changed events into the iframe so the dashboard can
  // re-fetch CSVs / other artifacts edited from the artifact viewer.
  useEffect(() => {
    const unsubscribe = wsClient.on('artifact.changed', (payload: WSMessage) => {
      const d = payload as {
        scope?: string;
        conversation_id?: number;
        module?: string;
        path?: string;
      };
      // If this is a module-scope change, filter to our module.
      if (d.scope === 'module' && d.module && d.module !== moduleName) return;
      postToIframe({
        type: 'artifact:change',
        scope: d.scope,
        conversationId: d.conversation_id,
        module: d.module,
        path: d.path,
      });
    });
    return () => {
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moduleName]);
}
