import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { emitEmbinderPhase } from '@embinder/react';

const DIRECT_MODULE = 'module_template';
type DirectDescriptor = {
  name: string;
  kind: 'read' | 'action';
  description: string;
  read?: () => unknown;
  act?: (args: Record<string, unknown>) => unknown | Promise<unknown>;
};
const directDescriptors = new Map<string, DirectDescriptor>();

function publicDescriptors() {
  return [...directDescriptors.values()].map(({ name, kind, description }) => ({ name, kind, description }));
}

function publishDirectRegistry() {
  window.dispatchEvent(new CustomEvent('minder:ui-sdk:register', {
    detail: { module: DIRECT_MODULE, descriptors: publicDescriptors() },
  }));
}

function useDirectDescriptor(descriptor: DirectDescriptor) {
  const latest = useRef(descriptor);
  latest.current = descriptor;
  useEffect(() => {
    directDescriptors.set(descriptor.name, {
      name: descriptor.name,
      kind: descriptor.kind,
      description: descriptor.description,
      read: () => latest.current.read?.(),
      act: (args) => latest.current.act?.(args),
    });
    publishDirectRegistry();
    return () => {
      directDescriptors.delete(descriptor.name);
      publishDirectRegistry();
    };
  }, [descriptor.name, descriptor.kind, descriptor.description]);
}

export interface MinderTokens {
  bg: string;
  text: string;
  textMuted: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  primary: string;
  secondary: string;
  info: string;
  success: string;
  warning: string;
  error: string;
  brandGradient: string;
  titleGradient: string;
  cardShadow: string;
  chart: string[];
}

export const DEFAULT_TOKENS: MinderTokens = {
  bg: '#0b1020', text: '#f4f7ff', textMuted: '#9ca8c8', surface: '#141b31',
  surfaceAlt: '#1b2540', border: '#2b3758', primary: '#2e6bf6', secondary: '#8b5cf6',
  info: '#38bdf8', success: '#34d399', warning: '#fbbf24', error: '#fb7185',
  brandGradient: 'linear-gradient(135deg, #2e6bf6, #8b5cf6)',
  titleGradient: 'linear-gradient(90deg, #f4f7ff, #9bbcff)',
  cardShadow: '0 12px 32px rgba(0, 0, 0, 0.28)',
  chart: ['#2e6bf6', '#8b5cf6', '#34d399', '#fbbf24', '#fb7185'],
};

const ThemeContext = createContext(DEFAULT_TOKENS);

export function MinderThemeProvider({ children }: { children: ReactNode; theme?: unknown }) {
  return <ThemeContext.Provider value={DEFAULT_TOKENS}>{children}</ThemeContext.Provider>;
}

export function useMinderTheme(): { tokens: MinderTokens } {
  return { tokens: useContext(ThemeContext) };
}

export interface DashboardProps { apiBase?: string; activeTab?: string; theme?: unknown }
export interface DashboardComponent extends React.FC<DashboardProps> {
  meta?: { title: string; tabs: TabMeta[] };
}
export interface TabMeta { id: string; label: string; icon?: string }

export function normalizeDashboardProps(props: DashboardProps): { apiBase: string; activeTab: string | undefined } {
  return { apiBase: props.apiBase ?? '', activeTab: props.activeTab };
}

function Page({ name, description, children }: { name: string; description: string; children: ReactNode }) {
  return <div data-embinder-scope={name} data-embinder-summary={description}>{children}</div>;
}

function Data({ name, description, value, children }: { name: string; description: string; value: unknown; children: ReactNode }) {
  useDirectDescriptor({ name, kind: 'read', description, read: () => value });
  return <div data-embinder-context={name} data-embinder-description={description} data-embinder-value={JSON.stringify(value)}>{children}</div>;
}

function Button({ name, description, onAct, children, embinderBind, style }: { name: string; description: string; onAct: () => void; children: ReactNode; embinderBind?: { 'data-embinder-tool': string }; style?: CSSProperties }) {
  useDirectDescriptor({ name, kind: 'action', description, act: () => onAct() });
  return <button type="button" {...embinderBind} data-embinder-tool={name} aria-label={description} onClick={onAct} style={{
    appearance: 'none', border: 0, borderRadius: 8, padding: '10px 14px', cursor: 'pointer',
    background: 'linear-gradient(135deg, #2e6bf6, #8b5cf6)', color: '#fff', fontWeight: 700,
    boxShadow: '0 8px 18px rgba(46, 107, 246, 0.25)', ...style,
  }}>{children}</button>;
}

export const Agent = { Page, Data, Button };

export function AgentDriverProvider({ children }: { children: ReactNode; apiBase?: string; onNavigate?: (route: string) => void }) {
  return <>{children}</>;
}

export function AgentRegistryProvider({ children }: { children: ReactNode; apiBase?: string; sessionId?: string }) {
  // EmbinderProvider always opens its WebMCP relay socket. This integration is
  // relay-free: Minder owns chat/tool execution while the SDK draws the cursor.
  useEffect(() => {
    const onRequest = () => publishDirectRegistry();
    const onInvoke = async (event: Event) => {
      const detail = (event as CustomEvent<{ request_id?: string; module?: string; action?: string; args?: Record<string, unknown> }>).detail;
      if (!detail?.request_id || detail.module !== DIRECT_MODULE || !detail.action) return;
      try {
        const descriptor = directDescriptors.get(detail.action);
        if (detail.action !== '__describe__' && !descriptor?.act) throw new Error('ui_action_not_registered');
        if (detail.action !== '__describe__') {
          emitEmbinderPhase({ type: 'focus', name: detail.action });
        }
        const output = detail.action === '__describe__'
          ? {
              descriptors: publicDescriptors(),
              context: Object.fromEntries([...directDescriptors.values()]
                .filter((item) => item.kind === 'read')
                .map((item) => [item.name, item.read?.()])),
            }
          : await descriptor.act!(detail.args ?? {});
        window.dispatchEvent(new CustomEvent('minder:ui-sdk:result', { detail: { request_id: detail.request_id, success: true, output } }));
      } catch (error) {
        window.dispatchEvent(new CustomEvent('minder:ui-sdk:result', { detail: { request_id: detail.request_id, success: false, error: String(error) } }));
      }
    };
    window.addEventListener('minder:ui-sdk:request-register', onRequest);
    window.addEventListener('minder:ui-sdk:invoke', onInvoke);
    publishDirectRegistry();
    return () => {
      window.removeEventListener('minder:ui-sdk:request-register', onRequest);
      window.removeEventListener('minder:ui-sdk:invoke', onInvoke);
    };
  }, []);
  return <>{children}</>;
}

export function AgentPresence(): null { return null; }

export function useAgentForm<T>(): {
  agentFilled: Array<keyof T>;
  pendingConfirm: null;
  focusField: keyof T | null;
  confirm: () => void;
  reject: () => void;
} {
  return { agentFilled: [], pendingConfirm: null, focusField: null, confirm: () => {}, reject: () => {} };
}

export function useAgentActivity(): undefined { return undefined; }

type QuickChat = { phase: 'idle' | 'thinking' | 'streaming' | 'done' | 'error'; text: string; ask: (text: string) => void; reset: () => void };
export function useQuickChat(): QuickChat {
  const [state, setState] = useState<Omit<QuickChat, 'ask' | 'reset'>>({ phase: 'idle', text: '' });
  useEffect(() => {
    const onReply = (event: Event) => {
      const detail = (event as CustomEvent<{ phase?: QuickChat['phase']; text?: string }>).detail;
      if (detail?.phase) setState({ phase: detail.phase, text: detail.text ?? '' });
    };
    window.addEventListener('minder:quickchat:reply', onReply);
    return () => window.removeEventListener('minder:quickchat:reply', onReply);
  }, []);
  return useMemo(() => ({
    ...state,
    ask: (text: string) => {
      setState({ phase: 'thinking', text: '' });
      window.dispatchEvent(new CustomEvent('minder:quickchat:send', { detail: { id: crypto.randomUUID(), text } }));
    },
    reset: () => setState({ phase: 'idle', text: '' }),
  }), [state]);
}
