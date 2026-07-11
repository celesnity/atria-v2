export const COLORS = {
  primary: '#6366f1',
  secondary: '#8b5cf6',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
  info: '#3b82f6',
  bg: '#0f0f1a',
  surface: '#1a1a2e',
  border: '#2d2d44',
  text: '#e2e8f0',
  muted: '#94a3b8',
};

export const STATUS_COLORS: Record<string, string> = {
  queued: '#f59e0b',
  running: '#6366f1',
  done: '#22c55e',
  error: '#ef4444',
};

export const CHART_COLORS = ['#6366f1', '#8b5cf6', '#22c55e', '#f59e0b', '#ef4444', '#3b82f6'];

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
