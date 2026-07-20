import {
  AgentDiv,
  AgentScope,
  EmbinderProvider,
  useEmbinder,
} from '@embinder/react';
import {
  cloneElement,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from 'react';

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
  return <AgentScope name={name} summary={() => ({ description })}>{children}</AgentScope>;
}

function Data({ name, description, value, children }: { name: string; description: string; value: unknown; children: ReactNode }) {
  return <AgentDiv name={name} description={description} context={() => value}>{children}</AgentDiv>;
}

function Button({ name, description, onAct, children }: { name: string; description: string; onAct: () => void; children: ReactElement }) {
  const bind = useEmbinder({ name, description, handler: () => onAct() });
  return cloneElement(children, { ...bind, onClick: (event: React.MouseEvent) => {
    children.props.onClick?.(event);
    if (!event.defaultPrevented) onAct();
  } });
}

export const Agent = { Page, Data, Button };

export function AgentDriverProvider({ children }: { children: ReactNode; apiBase?: string; onNavigate?: (route: string) => void }) {
  return <>{children}</>;
}

export function AgentRegistryProvider({ children }: { children: ReactNode; apiBase?: string; sessionId?: string }) {
  return <EmbinderProvider viz={false} chat={false}><EmbinderGhostCursor />{children}</EmbinderProvider>;
}

function EmbinderGhostCursor(): null {
  const cursor = useRef<{ handle: (phase: object) => void; destroy: () => void }>();
  useEffect(() => {
    let disposed = false;
    void import('@embinder/ghost-cursor').then(({ createGhostCursor }) => {
      if (disposed) return;
      cursor.current = createGhostCursor();
    });
    const onPhase = (event: Event) => cursor.current?.handle((event as CustomEvent).detail);
    window.addEventListener('minder:embinder-phase', onPhase);
    return () => {
      disposed = true;
      window.removeEventListener('minder:embinder-phase', onPhase);
      cursor.current?.destroy();
    };
  }, []);
  return null;
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

export function useModuleEvents(apiBase: string): { connected: boolean } {
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!apiBase) return;
    const stream = new EventSource(`${apiBase.replace(/\/$/, '')}/connector/events`);
    stream.onopen = () => setConnected(true);
    stream.onerror = () => setConnected(false);
    return () => stream.close();
  }, [apiBase]);
  return { connected };
}

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
