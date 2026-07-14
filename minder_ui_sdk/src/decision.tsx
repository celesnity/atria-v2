import { useCallback, useState, type ReactElement } from 'react';
import { useMinderTheme } from './theme';

/**
 * The human-in-the-loop surface (backlog "D"): the UI half of the module SDK's
 * `decision_packet` card. An agent proposes an action; a human approves,
 * modifies, or rejects it, and the decision is posted back in a structured form
 * the agent can execute and learn from.
 */

/** One entry of the assumption ledger the agent attaches to a proposal. */
export interface Assumption {
  text: string;
  confidence?: number | null;
  confidence_band?: 'low' | 'medium' | 'high' | null;
}

/** A proposed action packaged for approval — mirrors `cards.decision_packet`. */
export interface DecisionPacketData {
  card_type?: string;
  kind?: string;
  action: string;
  arguments: Record<string, unknown>;
  title?: string;
  summary?: string | null;
  assumptions?: Assumption[];
  risk?: string;
  reversible?: boolean | null;
  undo?: string | null;
  preview?: unknown;
}

export type DecisionVerdict = 'approve' | 'modify' | 'reject';

export interface Decision {
  verdict: DecisionVerdict;
  action: string;
  /** For 'modify': the edited arguments the human approved instead. */
  arguments?: Record<string, unknown>;
  note?: string;
}

type ColorToken = 'success' | 'warning' | 'error';
const RISK_COLOR: Record<string, ColorToken> = {
  none: 'success',
  low: 'success',
  medium: 'warning',
  high: 'warning',
  critical: 'error',
};

/**
 * POST a human decision back to the module. Returns a `submit` callback plus
 * `pending`/`error` state. Defaults to `${apiBase}/connector/decision`.
 */
export function useDecision(
  apiBase: string,
  opts: { path?: string; headers?: Record<string, string> } = {},
): {
  submit: (d: Decision) => Promise<Response>;
  pending: boolean;
  error: string | null;
} {
  const { path = '/connector/decision', headers } = opts;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(
    async (decision: Decision) => {
      setPending(true);
      setError(null);
      try {
        const res = await fetch(`${apiBase.replace(/\/$/, '')}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(headers ?? {}) },
          body: JSON.stringify(decision),
        });
        if (!res.ok) throw new Error(`decision ${res.status}`);
        return res;
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
        throw e;
      } finally {
        setPending(false);
      }
    },
    [apiBase, path, headers],
  );

  return { submit, pending, error };
}

/**
 * Render a decision packet with Approve / Modify / Reject controls. Supply
 * `onDecision` (e.g. from `useDecision().submit`) to receive the human's choice.
 */
export function DecisionPacket({
  packet,
  onDecision,
  pending,
}: {
  packet: DecisionPacketData;
  onDecision: (d: Decision) => void;
  pending?: boolean;
}): ReactElement {
  const { tokens } = useMinderTheme();
  const [note, setNote] = useState('');
  const risk = packet.risk ?? 'low';
  const riskColor = tokens[RISK_COLOR[risk] ?? 'warning'] as string;

  const decide = (verdict: DecisionVerdict) =>
    onDecision({ verdict, action: packet.action, arguments: packet.arguments, note: note || undefined });

  return (
    <div
      data-minder-decision=""
      style={{
        background: tokens.surface,
        border: `1px solid ${tokens.border}`,
        borderRadius: 12,
        padding: 16,
        color: tokens.text,
        boxShadow: tokens.cardShadow,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <strong style={{ fontSize: 15 }}>{packet.title ?? packet.action}</strong>
        <span
          style={{
            marginLeft: 'auto',
            fontSize: 11,
            fontWeight: 700,
            textTransform: 'uppercase',
            color: riskColor,
            border: `1px solid ${riskColor}`,
            borderRadius: 999,
            padding: '2px 8px',
          }}
        >
          {risk} risk
        </span>
        {packet.reversible != null ? (
          <span style={{ fontSize: 11, color: tokens.textMuted }}>
            {packet.reversible ? '↩ reversible' : '⚠ irreversible'}
          </span>
        ) : null}
      </div>

      {packet.summary ? (
        <p style={{ margin: 0, color: tokens.textMuted, fontSize: 13 }}>{packet.summary}</p>
      ) : null}

      {packet.assumptions && packet.assumptions.length > 0 ? (
        <div>
          <div style={{ fontSize: 12, color: tokens.textMuted, marginBottom: 4 }}>
            Assumptions
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
            {packet.assumptions.map((a, i) => (
              <li key={i}>
                {a.text}
                {a.confidence != null ? (
                  <span style={{ color: tokens.textMuted }}> ({Math.round(a.confidence * 100)}%)</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {Object.keys(packet.arguments ?? {}).length > 0 ? (
        <pre
          style={{
            margin: 0,
            background: tokens.surfaceAlt,
            border: `1px solid ${tokens.border}`,
            borderRadius: 8,
            padding: 10,
            fontSize: 12,
            overflow: 'auto',
          }}
        >
          {JSON.stringify(packet.arguments, null, 2)}
        </pre>
      ) : null}

      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Add a note (optional)…"
        style={{
          background: tokens.surfaceAlt,
          border: `1px solid ${tokens.border}`,
          borderRadius: 8,
          padding: '8px 10px',
          color: tokens.text,
          fontSize: 13,
        }}
      />

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          disabled={pending}
          onClick={() => decide('approve')}
          style={btn(tokens.success, pending)}
        >
          Approve
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => decide('modify')}
          style={btn(tokens.warning, pending)}
        >
          Modify
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => decide('reject')}
          style={btn(tokens.error, pending)}
        >
          Reject
        </button>
      </div>
    </div>
  );
}

function btn(color: string, disabled?: boolean): React.CSSProperties {
  return {
    flex: 1,
    padding: '9px 12px',
    borderRadius: 8,
    border: `1px solid ${color}`,
    background: 'transparent',
    color,
    fontWeight: 600,
    fontSize: 13,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
  };
}
