import type { TabMeta } from 'minder-ui-sdk';

// Persona-based tabs (hybrid: persona route -> epic panels inside).
export const TABS: TabMeta[] = [
  { id: 'operator', label: 'Operator', icon: 'user' },
  { id: 'leader', label: 'Tổ trưởng', icon: 'users' },
  { id: 'supervisor', label: 'Quản ca', icon: 'clipboard-check' },
  { id: 'manager', label: 'Quản lý xưởng', icon: 'bar-chart' },
  { id: 'admin', label: 'FDE / Admin', icon: 'settings' },
];
