import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactElement,
  type ReactNode,
} from 'react';
import { useAgentActivity } from '../agentDriver';
import { createRegistry, type Registry } from './registry';

const RegistryCtx = createContext<Registry | null>(null);
const PageCtx = createContext<string | null>(null);

function scoped(page: string | null, name: string): string {
  return page ? `${page}.${name}` : name;
}

export interface AgentRegistryProviderProps {
  apiBase?: string;
  sessionId?: string;
  children: ReactNode;
}

export function AgentRegistryProvider({
  apiBase,
  sessionId = 'default',
  children,
}: AgentRegistryProviderProps): ReactElement {
  const ref = useRef<Registry | null>(null);
  if (!ref.current) ref.current = createRegistry();
  const reg = ref.current;

  // Act path: react to the driver's latest intent.
  const activity = useAgentActivity();
  useEffect(() => {
    const i = activity?.intent;
    if (i && i.intent === 'act') reg.run(i.name);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activity?.tick]);

  // Read path: push a debounced snapshot on every change.
  useEffect(() => {
    if (!apiBase) return;
    const base = apiBase.replace(/\/$/, '');
    let timer: ReturnType<typeof setTimeout> | null = null;
    const push = (): void => {
      void fetch(`${base}/connector/ui/snapshot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, snapshot: reg.snapshot() }),
      }).catch(() => {});
    };
    const schedule = (): void => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(push, 150);
    };
    const unsub = reg.subscribe(schedule);
    schedule();
    return () => {
      if (timer) clearTimeout(timer);
      unsub();
    };
  }, [apiBase, sessionId, reg]);

  return <RegistryCtx.Provider value={reg}>{children}</RegistryCtx.Provider>;
}

function useRegistry(): Registry | null {
  return useContext(RegistryCtx);
}

function AgentPage({
  name,
  children,
}: {
  name: string;
  description?: string;
  children: ReactNode;
}): ReactElement {
  const reg = useRegistry();
  useEffect(() => {
    reg?.setPage(name);
    return () => {
      if (reg?.getPage() === name) reg.setPage(null);
    };
  }, [reg, name]);
  return <PageCtx.Provider value={name}>{children}</PageCtx.Provider>;
}

function AgentData({
  name,
  description,
  value,
  children,
}: {
  name: string;
  description?: string;
  value: unknown;
  children: ReactNode;
}): ReactElement {
  const reg = useRegistry();
  const page = useContext(PageCtx);
  const full = scoped(page, name);
  useEffect(() => {
    reg?.setData({ name: full, description, value });
    return () => reg?.removeData(full);
  }, [reg, full, description, value]);
  return <>{children}</>;
}

function AgentButton({
  name,
  description,
  onAct,
  children,
}: {
  name: string;
  description?: string;
  onAct: () => void | Promise<void>;
  children: ReactNode;
}): ReactElement {
  const reg = useRegistry();
  const page = useContext(PageCtx);
  const full = scoped(page, name);
  const onActRef = useRef(onAct);
  onActRef.current = onAct;
  useEffect(() => {
    reg?.setAction({ name: full, description, onAct: () => onActRef.current() });
    return () => reg?.removeAction(full);
  }, [reg, full, description]);
  return (
    <span data-agent-control={full} style={{ display: 'contents' }}>
      {children}
    </span>
  );
}

export const Agent = { Page: AgentPage, Data: AgentData, Button: AgentButton };
