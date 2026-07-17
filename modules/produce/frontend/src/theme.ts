import type { MinderTokens } from 'minder-ui-sdk';

/** Map a produce status string to a token color. */
export function statusColor(tokens: MinderTokens, status: string): string {
  switch (status) {
    case 'queued': case 'idle': case 'open': case 'draft':
      return tokens.warning;
    case 'assigned': case 'in_progress': case 'running': case 'triaged': case 'setup':
      return tokens.primary;
    case 'done': case 'resolved': case 'approved': case 'released': case 'acknowledged':
      return tokens.success;
    case 'blocked': case 'down': case 'held': case 'escalated': case 'aborted': case 'retired':
      return tokens.error;
    default:
      return tokens.textMuted;
  }
}
