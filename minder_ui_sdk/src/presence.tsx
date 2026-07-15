import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactElement,
} from 'react';
import { useMinderTheme } from './theme';
import { useModuleEvents, type EventActor } from './agentContext';
import { useAgentActivity, type UiIntent } from './agentDriver';

/**
 * The Agent Presence Layer (stage, not steering wheel). This is the *animation*
 * half of the co-pilot: it narrates what Minder just did — or is proposing — as
 * a ghost cursor + caption, driven entirely by signals that already happened on
 * the backend. It never calls a state-changing API; disabling this layer leaves
 * the agent fully functional through the backend SDK (UI-SDK-03/12).
 *
 * Two signals, matched to the autonomy ladder:
 *  - a *committed* low/medium-risk action arrives as an `action.completed`
 *    envelope → presence animates it as **done** (UI-SDK-02/07).
 *  - a high-risk action is a *proposal*: the agent's `request_confirm` intent →
 *    the ghost cursor parks over the Approve control and waits for the human to
 *    click; the SDK never clicks it (UI-SDK-08).
 * The operator can dismiss/interrupt the presence at any moment (UI-SDK-09).
 */

export type AgentPresenceState = 'idle' | 'acting' | 'proposing';

export interface AgentPresenceInfo {
  state: AgentPresenceState;
  /** Who the presence attributes the action to (agent vs human). */
  actor: EventActor | null;
  /** Risk band of the underlying action, when known. */
  risk: string | null;
  /** One-line narration to render beside the cursor. */
  caption: string;
  /** CSS selector the ghost cursor should point at (the field/control/button the
   * agent is touching — proposing → Approve). Null → the cursor rests in the
   * corner (e.g. a committed action with no on-screen anchor). */
  target: string | null;
  /** Bumped on every new signal so the cursor re-measures its target even when
   * the selector is unchanged (the element may have just mounted after a nav). */
  nonce: number;
  /** Operator interrupt — clears the presence immediately (UI-SDK-09). */
  dismiss: () => void;
}

const IDLE: Omit<AgentPresenceInfo, 'dismiss'> = {
  state: 'idle',
  actor: null,
  risk: null,
  caption: '',
  target: null,
  nonce: 0,
};

/** The on-screen element an intent points at, using the data-attributes a module
 * frontend already sets on agent-drivable fields/forms/controls. */
function targetForIntent(intent: UiIntent, approveSelector: string): string | null {
  switch (intent.intent) {
    case 'focus':
      return intent.field ? `[data-agent-field="${intent.field}"]` : null;
    case 'fill': {
      const keys = Object.keys(intent.values ?? {});
      return keys.length
        ? `[data-agent-field="${keys[keys.length - 1]}"]`
        : `[data-agent-form="${intent.form}"]`;
    }
    case 'highlight':
      return `[data-agent-control="${intent.control}"],[data-agent-field="${intent.control}"]`;
    case 'request_confirm':
      return approveSelector;
    case 'submit':
      return `[data-agent-control="submit"],${approveSelector}`;
    case 'navigate':
    default:
      return null;
  }
}

/** One-line narration for an intent. */
function captionForIntent(intent: UiIntent): string {
  switch (intent.intent) {
    case 'navigate':
      return 'Minder opened this screen';
    case 'fill':
      return 'Minder filled the form';
    case 'focus':
      return 'Fill this next';
    case 'highlight':
      return 'Minder points here';
    case 'submit':
      return 'Submitting…';
    default:
      return 'Minder is here';
  }
}

export interface UseAgentPresenceOptions {
  /** How long a "done" animation lingers before fading, ms. Default 3500. */
  holdMs?: number;
  /** Selector the cursor parks at for a proposal. Default `[data-minder-approve]`. */
  approveSelector?: string;
}

/**
 * Derive the current agent presence from committed events + proposal intents.
 * Self-contained: subscribes to the module event stream and (when mounted under
 * an `AgentDriverProvider`) reads the latest UI intent. Returns `state: 'idle'`
 * when the agent is quiet — render nothing in that case.
 */
export function useAgentPresence(
  apiBase: string,
  opts: UseAgentPresenceOptions = {},
): AgentPresenceInfo {
  const { holdMs = 3500, approveSelector = '[data-minder-approve]' } = opts;
  const activity = useAgentActivity();
  const [info, setInfo] = useState<Omit<AgentPresenceInfo, 'dismiss'>>(IDLE);
  // Ticks the operator dismissed, so a dismissed proposal doesn't re-appear.
  const dismissedTick = useRef<number>(-1);
  const seq = useRef<number>(0);
  const set = useCallback((next: Omit<AgentPresenceInfo, 'dismiss' | 'nonce'>) => {
    seq.current += 1;
    setInfo({ ...next, nonce: seq.current });
  }, []);

  // Committed actions → "Minder did X" (only animate what actually happened).
  useModuleEvents(apiBase, {
    types: ['action.completed', 'action.failed'],
    onEvent: (env) => {
      const tool = (env.payload as { tool?: string })?.tool ?? 'an action';
      const failed = env.type === 'action.failed';
      set({
        state: 'acting',
        actor: env.actor ?? { kind: 'agent' },
        risk: (env.payload as { risk?: string })?.risk ?? null,
        caption: `Minder ${failed ? 'tried' : 'did'}: ${tool}`,
        target: null,
      });
    },
  });

  // Live intents drive the cursor to the actual component the agent is touching:
  // fill/focus/highlight/submit → point at that field/control; request_confirm →
  // park at Approve and wait (proposal). navigate carries no anchor.
  useEffect(() => {
    if (!activity || dismissedTick.current === activity.tick) return;
    const it = activity.intent;
    if (it.intent === 'request_confirm') {
      set({
        state: 'proposing',
        actor: { kind: 'agent' },
        risk: 'high',
        caption: it.summary || 'Minder proposes an action — your approval',
        target: approveSelector,
      });
    } else {
      set({
        state: 'acting',
        actor: { kind: 'agent' },
        risk: 'low',
        caption: captionForIntent(it),
        target: targetForIntent(it, approveSelector),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activity, approveSelector]);

  // An 'acting' narration lingers then fades; a 'proposing' one stays until the
  // human acts on it or the operator dismisses it.
  useEffect(() => {
    if (info.state !== 'acting') return;
    const t = setTimeout(() => setInfo(IDLE), holdMs);
    return () => clearTimeout(t);
  }, [info, holdMs]);

  const dismiss = useCallback(() => {
    if (activity) dismissedTick.current = activity.tick;
    setInfo(IDLE);
  }, [activity]);

  return { ...info, dismiss };
}

/** Human-readable attribution: distinguishes "Minder did" from "you did"
 * (UI-SDK-06). Never claims a human action for the agent or vice-versa. */
export function attributionLabel(actor?: EventActor | null): string {
  if (!actor) return 'System';
  if (actor.kind === 'agent') return 'Minder';
  if (actor.kind === 'human') return actor.on_behalf_of || 'You';
  return 'System';
}

/** A small pill badging who acted — accent for the agent, neutral for a human. */
export function AgentBadge({ actor }: { actor?: EventActor | null }): ReactElement {
  const { tokens } = useMinderTheme();
  const isAgent = actor?.kind === 'agent';
  const color = isAgent ? tokens.primary : tokens.textMuted;
  return (
    <span
      data-minder-attribution={actor?.kind ?? 'system'}
      style={{
        fontSize: 11,
        fontWeight: 700,
        color,
        border: `1px solid ${color}`,
        borderRadius: 999,
        padding: '1px 8px',
      }}
    >
      {attributionLabel(actor)}
    </span>
  );
}

/** Track a target element's viewport position, re-measuring as it appears/moves.
 *
 * Robust to the element not existing yet (it polls briefly after a nav mounts the
 * panel) and to the page scrolling/resizing while the cursor is parked. `nonce`
 * forces a fresh measure even when `selector` is unchanged. */
function useTrackedPosition(
  selector: string | null,
  nonce: number,
): { x: number; y: number } | null {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  useEffect(() => {
    if (!selector || typeof document === 'undefined') {
      setPos(null);
      return;
    }
    let raf = 0;
    let cancelled = false;
    let last: { x: number; y: number } | null = null;
    const measure = (): void => {
      const el = document.querySelector(selector) as HTMLElement | null;
      if (!el) return;
      const r = el.getBoundingClientRect();
      // A freshly-mounted element that is still animating in can report a zero
      // box — skip it so the cursor doesn't snap to (0,0) then jump.
      if (r.width === 0 && r.height === 0) return;
      // Point just inside the element's leading edge (feels like the cursor
      // landed on it), vertically centred.
      const next = { x: r.left + Math.min(20, r.width / 2), y: r.top + r.height / 2 };
      if (!last || Math.abs(last.x - next.x) > 0.5 || Math.abs(last.y - next.y) > 0.5) {
        last = next;
        setPos(next);
      }
    };
    // Follow the target continuously while active. Panels crossfade, rows
    // animate in (framer-motion), and layout shifts as content loads — a
    // one-shot measure would leave the cursor parked at the element's initial
    // (pre-animation) position instead of where it finally settles. setPos only
    // fires on real movement, so once settled this idles without re-rendering.
    const loop = () => {
      if (cancelled) return;
      measure();
      raf = requestAnimationFrame(loop);
    };
    loop();
    return () => {
      cancelled = true;
      if (raf) cancelAnimationFrame(raf);
    };
  }, [selector, nonce]);
  return pos;
}

/** The ghost cursor itself — an absolutely-positioned pointer that glides to the
 * component the agent is touching, or rests in the corner. Presentational only. */
export function GhostCursor({
  state,
  target,
  nonce = 0,
}: {
  state: AgentPresenceState;
  target: string | null;
  nonce?: number;
}): ReactElement | null {
  const { tokens } = useMinderTheme();
  const pos = useTrackedPosition(state === 'idle' ? null : target, nonce);
  if (state === 'idle') return null;
  const color = state === 'proposing' ? tokens.warning : tokens.primary;
  const style: React.CSSProperties = pos
    ? // Offset so the pointer's tip (top-left of the SVG), not its box, sits on
      // the measured point.
      { position: 'fixed', left: pos.x, top: pos.y, transform: 'translate(-4px, -2px)' }
    : { position: 'fixed', right: 24, bottom: 24 };
  return (
    <div
      data-minder-ghost-cursor={state}
      aria-hidden
      style={{
        ...style,
        pointerEvents: 'none',
        zIndex: 9999,
        transition: 'left 420ms ease, top 420ms ease',
        color,
        filter: `drop-shadow(0 1px 2px ${tokens.cardShadow})`,
        animation: state === 'proposing' ? 'minder-ghost-pulse 1.2s ease-in-out infinite' : undefined,
      }}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill={color} aria-hidden>
        <path d="M4 2l6 16 2.5-6.5L19 9 4 2z" />
      </svg>
    </div>
  );
}

export interface AgentPresenceProps extends UseAgentPresenceOptions {
  apiBase: string;
}

/**
 * Drop-in presence overlay: the ghost cursor + a caption chip with attribution
 * and a dismiss control. Renders nothing while the agent is idle. Read-only —
 * turning it off doesn't change what the agent can do (UI-SDK-12).
 */
export function AgentPresence(props: AgentPresenceProps): ReactElement | null {
  const { apiBase, ...opts } = props;
  const info = useAgentPresence(apiBase, opts);
  const { tokens } = useMinderTheme();
  if (info.state === 'idle') return null;
  const accent = info.state === 'proposing' ? tokens.warning : tokens.primary;
  return (
    <>
      <style>{'@keyframes minder-ghost-pulse{0%,100%{opacity:1}50%{opacity:.45}}'}</style>
      <GhostCursor state={info.state} target={info.target} nonce={info.nonce} />
      <div
        data-minder-presence={info.state}
        style={{
          position: 'fixed',
          right: 24,
          bottom: 56,
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          maxWidth: 320,
          background: tokens.surface,
          border: `1px solid ${accent}`,
          borderRadius: 999,
          padding: '6px 10px 6px 12px',
          color: tokens.text,
          boxShadow: tokens.cardShadow,
          fontSize: 13,
        }}
      >
        <AgentBadge actor={info.actor} />
        <span style={{ color: tokens.textMuted }}>{info.caption}</span>
        <button
          type="button"
          onClick={info.dismiss}
          aria-label="Dismiss Minder"
          data-minder-presence-dismiss=""
          style={{
            marginLeft: 4,
            border: 'none',
            background: 'transparent',
            color: tokens.textMuted,
            cursor: 'pointer',
            fontSize: 15,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>
    </>
  );
}
