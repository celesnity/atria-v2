import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type ReactElement,
} from 'react';

/**
 * The agent-drives-the-real-UI surface (declarative co-pilot). The module
 * declares pages/forms/controls in the module SDK; the agent emits typed
 * `UiIntent`s over a per-session bus; this provider applies them to the module's
 * actual React components. The human still fills blanks and confirms — the agent
 * proposes, prefills, and points, but does not click "submit" on a risky action
 * by itself.
 */

export type UiIntent =
  | { intent: 'navigate'; route: string }
  | { intent: 'fill'; form: string; values: Record<string, unknown>; partial?: boolean }
  | { intent: 'focus'; form?: string | null; field: string }
  | { intent: 'highlight'; control: string }
  | { intent: 'request_confirm'; target: string; summary?: string | null }
  | { intent: 'submit'; form: string };

/** Internal per-form handler the provider dispatches intents to. */
interface FormController {
  fill(values: Record<string, unknown>, partial: boolean): void;
  focus(field: string): void;
  requestConfirm(summary: string | null): void;
  submit(): void;
}

/** The most recent intent the driver dispatched, with a monotonic tick so
 * consumers (e.g. a mascot) can re-animate even on a repeat of the same type. */
export interface AgentActivity {
  intent: UiIntent;
  tick: number;
}

interface DriverContextValue {
  register(formId: string, ctl: FormController): () => void;
  highlighted: string | null;
  activity: AgentActivity | null;
}

const DriverContext = createContext<DriverContextValue | null>(null);

export interface AgentDriverProviderProps {
  apiBase: string;
  /** Session whose bus to subscribe to; matches the `session` query param. */
  sessionId?: string;
  /** SSE path relative to `apiBase`. Defaults to `/connector/ui/intents`. */
  path?: string;
  /** Called on a `navigate` intent — wire this to your router. */
  onNavigate?: (route: string) => void;
  /** Called for every intent — use for cross-cutting reactions (e.g. a mascot). */
  onIntent?: (intent: UiIntent) => void;
  children: ReactNode;
}

/**
 * Subscribe to the module's UI-intent bus and dispatch each intent to the right
 * form (via `useAgentForm`) or to navigation. Wrap the module dashboard once.
 */
export function AgentDriverProvider({
  apiBase,
  sessionId,
  path = '/connector/ui/intents',
  onNavigate,
  onIntent,
  children,
}: AgentDriverProviderProps): ReactElement {
  const forms = useRef<Map<string, FormController>>(new Map());
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [activity, setActivity] = useState<AgentActivity | null>(null);
  const tick = useRef(0);
  const onNavigateRef = useRef(onNavigate);
  onNavigateRef.current = onNavigate;
  const onIntentRef = useRef(onIntent);
  onIntentRef.current = onIntent;

  const register = useCallback((formId: string, ctl: FormController) => {
    forms.current.set(formId, ctl);
    return () => {
      if (forms.current.get(formId) === ctl) forms.current.delete(formId);
    };
  }, []);

  useEffect(() => {
    if (!apiBase || typeof EventSource === 'undefined') return;
    const qs = sessionId ? `?session=${encodeURIComponent(sessionId)}` : '';
    const es = new EventSource(`${apiBase.replace(/\/$/, '')}${path}${qs}`);
    es.onmessage = (e: MessageEvent) => {
      let intent: UiIntent;
      try {
        intent = JSON.parse(e.data) as UiIntent;
      } catch {
        return;
      }
      dispatchIntent(intent, forms.current, onNavigateRef.current, setHighlighted);
      onIntentRef.current?.(intent);
      tick.current += 1;
      setActivity({ intent, tick: tick.current });
    };
    return () => es.close();
  }, [apiBase, sessionId, path]);

  return (
    <DriverContext.Provider value={{ register, highlighted, activity }}>
      {children}
    </DriverContext.Provider>
  );
}

function dispatchIntent(
  intent: UiIntent,
  forms: Map<string, FormController>,
  onNavigate: ((route: string) => void) | undefined,
  setHighlighted: (c: string | null) => void,
): void {
  switch (intent.intent) {
    case 'navigate':
      onNavigate?.(intent.route);
      break;
    case 'fill':
      forms.get(intent.form)?.fill(intent.values, intent.partial ?? true);
      break;
    case 'focus':
      if (intent.form) forms.get(intent.form)?.focus(intent.field);
      break;
    case 'highlight':
      setHighlighted(intent.control);
      break;
    case 'request_confirm':
      forms.get(intent.target)?.requestConfirm(intent.summary ?? null);
      break;
    case 'submit':
      forms.get(intent.form)?.submit();
      break;
  }
}

export interface UseAgentFormArgs<T> {
  /** Current form value (controlled). */
  value: T;
  /** Setter — the agent's `fill` intent calls this so the user SEES fields fill. */
  setValue: (next: T) => void;
  /** Run on `submit` / human confirm — typically POSTs the gated submit_tool. */
  onSubmit: () => void;
}

export interface AgentFormState {
  /** Field names the agent last prefilled (badge them as "agent-filled"). */
  agentFilled: string[];
  /** Set when the agent asked the human to confirm; render a confirm bar. */
  pendingConfirm: { summary: string | null } | null;
  /** Field the agent pointed the user at (e.g. the next blank). */
  focusField: string | null;
  /** Human accepts → runs onSubmit and clears the confirm. */
  confirm: () => void;
  /** Human rejects → clears the confirm without submitting. */
  reject: () => void;
}

/**
 * Bind a real form to the agent driver by id. The agent's `fill` intent merges
 * values into your state (leaving blanks for the user when `partial`), `focus`
 * points at a field, `request_confirm` raises `pendingConfirm`, and `submit`
 * (or the human's `confirm`) runs `onSubmit`.
 */
export function useAgentForm<T extends Record<string, unknown>>(
  formId: string,
  { value, setValue, onSubmit }: UseAgentFormArgs<T>,
): AgentFormState {
  const ctx = useContext(DriverContext);
  const [agentFilled, setAgentFilled] = useState<string[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<{ summary: string | null } | null>(null);
  const [focusField, setFocusField] = useState<string | null>(null);

  const valueRef = useRef(value);
  valueRef.current = value;
  const setValueRef = useRef(setValue);
  setValueRef.current = setValue;
  const onSubmitRef = useRef(onSubmit);
  onSubmitRef.current = onSubmit;

  useEffect(() => {
    if (!ctx) return;
    const ctl: FormController = {
      fill(values, partial) {
        const base = valueRef.current;
        // `partial` merges over current state (agent-provided keys win) so the
        // user's own edits to other fields survive.
        const merged = partial ? { ...base, ...values } : ({ ...values } as T);
        setValueRef.current(merged as T);
        setAgentFilled(Object.keys(values));
      },
      focus(field) {
        setFocusField(field);
      },
      requestConfirm(summary) {
        setPendingConfirm({ summary });
      },
      submit() {
        setPendingConfirm(null);
        onSubmitRef.current();
      },
    };
    return ctx.register(formId, ctl);
  }, [ctx, formId]);

  const confirm = useCallback(() => {
    setPendingConfirm(null);
    onSubmitRef.current();
  }, []);
  const reject = useCallback(() => setPendingConfirm(null), []);

  return { agentFilled, pendingConfirm, focusField, confirm, reject };
}

/** Read which control the agent last asked to highlight (for a pulse/ring). */
export function useAgentHighlight(): string | null {
  return useContext(DriverContext)?.highlighted ?? null;
}

/** Read the driver's latest activity — the last intent + a monotonic tick.
 * Drive a mascot / status indicator off this. */
export function useAgentActivity(): AgentActivity | null {
  return useContext(DriverContext)?.activity ?? null;
}
