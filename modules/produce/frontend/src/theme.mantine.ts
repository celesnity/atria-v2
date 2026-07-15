import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Cobalt scale centered on the Celesnity accent #2563EB (Mantine wants 10 shades).
const cobalt: MantineColorsTuple = [
  '#e7f0ff',
  '#cfdcfb',
  '#9db6f4',
  '#688eed',
  '#3f6de8',
  '#2559e6',
  '#1a51e5',
  '#0d42cc',
  '#023ab7',
  '#0031a1',
];

export const produceTheme = createTheme({
  primaryColor: 'cobalt',
  colors: { cobalt },
  defaultRadius: 'md',
  fontFamily:
    'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  headings: { fontFamily: 'inherit', sizes: { h5: { fontSize: '14px', fontWeight: '700' } } },
});

// Map a produce status string to a Mantine color name (used by Badge, etc.).
export function statusColorMantine(status: string): string {
  switch (status) {
    case 'queued':
    case 'idle':
    case 'open':
    case 'draft':
      return 'orange';
    case 'assigned':
    case 'in_progress':
    case 'running':
    case 'triaged':
    case 'setup':
      return 'cobalt';
    case 'done':
    case 'resolved':
    case 'approved':
    case 'released':
    case 'acknowledged':
      return 'green';
    case 'blocked':
    case 'down':
    case 'held':
    case 'escalated':
    case 'aborted':
    case 'retired':
      return 'red';
    default:
      return 'gray';
  }
}
