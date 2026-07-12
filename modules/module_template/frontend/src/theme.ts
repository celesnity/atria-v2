export const COLORS = {
  primary: '#2563EB',
  secondary: '#2E6BF6',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
  info: '#5AA6FF',
  bg: '#060711',
  surface: '#111A2E',
  border: '#22304D',
  text: '#e2e8f0',
  muted: '#94a3b8',
};

export const STATUS_COLORS: Record<string, string> = {
  queued: '#f59e0b',
  running: '#2563EB',
  done: '#22c55e',
  error: '#ef4444',
};

export const CHART_COLORS = ['#2563EB', '#2E6BF6', '#22c55e', '#f59e0b', '#ef4444', '#5AA6FF'];

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
