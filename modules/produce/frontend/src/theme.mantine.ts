import { createTheme, rem, type MantineColorsTuple } from '@mantine/core';

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

// Cool-tinted neutral ramp — replaces Mantine's stock pure-grays so cards,
// borders and muted text pick up the Celesnity indigo undertone instead of
// reading as flat white-on-white. Used as the default `gray` scale.
const slate: MantineColorsTuple = [
  '#f6f8fc',
  '#eef1f8',
  '#dfe4f0',
  '#c9d1e4',
  '#aeb9d4',
  '#8f9cc0',
  '#6f7da8',
  '#5a6690',
  '#3f4a6e',
  '#2a3352',
];

export const produceTheme = createTheme({
  primaryColor: 'cobalt',
  primaryShade: { light: 5, dark: 5 },
  colors: { cobalt, slate },
  white: '#ffffff',
  black: '#1b2440',
  defaultRadius: 'md',
  focusRing: 'auto',
  cursorType: 'pointer',
  fontFamily:
    'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  fontFamilyMonospace:
    'ui-monospace, "JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace',
  headings: {
    fontFamily: 'inherit',
    fontWeight: '700',
    sizes: {
      h4: { fontSize: rem(17), fontWeight: '700', lineHeight: '1.3' },
      h5: { fontSize: rem(14), fontWeight: '700', lineHeight: '1.35' },
    },
  },
  // Softer, cooler elevation than Mantine's stock grays — matches the
  // Celesnity daybreak shadow spec (cool navy tint, low spread).
  shadows: {
    xs: '0 1px 2px rgba(28, 34, 64, 0.06)',
    sm: '0 1px 2px rgba(28, 34, 64, 0.06), 0 3px 10px rgba(28, 34, 64, 0.05)',
    md: '0 4px 12px rgba(28, 34, 64, 0.08), 0 12px 24px rgba(28, 34, 64, 0.06)',
    lg: '0 8px 24px rgba(28, 34, 64, 0.10), 0 20px 40px rgba(28, 34, 64, 0.08)',
  },
  radius: { sm: rem(6), md: rem(10), lg: rem(14), xl: rem(20) },
  defaultGradient: { from: 'cobalt.7', to: 'cobalt.4', deg: 120 },
  components: {
    Card: {
      defaultProps: { withBorder: true, radius: 'lg', shadow: 'sm' },
      styles: {
        root: {
          borderColor: 'var(--pr-border, var(--mantine-color-gray-3))',
          backgroundColor: 'var(--pr-surface, var(--mantine-color-white))',
        },
      },
    },
    Button: {
      defaultProps: { radius: 'md' },
      styles: { root: { fontWeight: 600 } },
    },
    Badge: {
      defaultProps: { radius: 'sm', variant: 'light' },
      styles: { root: { fontWeight: 600, textTransform: 'none' } },
    },
    Divider: {
      styles: { root: { borderColor: 'var(--pr-border, var(--mantine-color-gray-2))' } },
    },
    Input: {
      styles: {
        input: {
          borderColor: 'var(--mantine-color-gray-3)',
          backgroundColor: 'var(--mantine-color-white)',
        },
      },
    },
    Table: {
      styles: { th: { textTransform: 'uppercase', fontSize: rem(11), letterSpacing: '0.03em' } },
    },
  },
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
