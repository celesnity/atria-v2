import type { MinderTokens } from './embinder';

/** Map a job/task status string to the appropriate token color. */
export function statusColor(tokens: MinderTokens, status: string): string {
  switch (status) {
    case 'queued':  return tokens.warning;
    case 'running': return tokens.primary;
    case 'done':    return tokens.success;
    case 'error':   return tokens.error;
    default:        return tokens.textMuted;
  }
}

export const variants = {
  listContainer: {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.07 },
    },
  },
  listItem: {
    hidden: { opacity: 0, y: 12 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.3 } },
    exit: { opacity: 0, x: -20, transition: { duration: 0.2 } },
  },
  panelVariants: {
    hidden: { opacity: 0, y: 16 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
    exit: { opacity: 0, y: -8, transition: { duration: 0.2 } },
  },
};
