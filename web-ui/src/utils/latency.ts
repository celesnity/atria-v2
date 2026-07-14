import type { Message } from '../types';

/** Format a millisecond duration for the latency footer: "850ms", "3.2s", "1m 05s". */
export function formatLatency(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const secs = ms / 1000;
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const mins = Math.floor(secs / 60);
  const rest = Math.round(secs % 60);
  return `${mins}m ${String(rest).padStart(2, '0')}s`;
}

/**
 * One-line latency summary for an assistant turn, or null when the turn has
 * no timing (e.g. history loaded from the server, which carries no metrics).
 */
export function latencySummary(metrics: Message['metrics']): string | null {
  if (!metrics || metrics.ttftMs === undefined) return null;
  const parts = [`first token ${formatLatency(metrics.ttftMs)}`];
  if (metrics.totalMs !== undefined) parts.push(`total ${formatLatency(metrics.totalMs)}`);
  return parts.join(' · ');
}
