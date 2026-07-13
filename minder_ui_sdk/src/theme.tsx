import { createContext, createElement, useContext, type ReactNode } from 'react';

/** The two Minder host skies, forwarded to modules as a simple mode. */
export type MinderTheme = 'light' | 'dark';

/**
 * Semantic design tokens a module paints with. Values are plain CSS strings so
 * inline styles (the module_template idiom) can consume them directly; `bg`,
 * `brandGradient` and `titleGradient` may be gradients.
 */
export interface MinderTokens {
  /** Page background — a radial gradient. */
  bg: string;
  /** Card / raised surface. */
  surface: string;
  /** Secondary surface (inputs, insets). */
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  primary: string;
  secondary: string;
  info: string;
  success: string;
  warning: string;
  error: string;
  /** Logo chip / accent fill. */
  brandGradient: string;
  /** Heading text gradient (use with -webkit-background-clip: text). */
  titleGradient: string;
  /** Resting card shadow. */
  cardShadow: string;
  /** Hover card shadow. */
  cardHoverShadow: string;
  /** Chart color series. */
  chart: string[];
}

const DARK: MinderTokens = {
  bg: 'radial-gradient(120% 90% at 15% 0%, #12245C 0%, #0A1030 42%, #060711 100%)',
  surface: '#111A2E',
  surfaceAlt: '#0E1626',
  border: '#22304D',
  text: '#e2e8f0',
  textMuted: '#94a3b8',
  primary: '#2563EB',
  secondary: '#2E6BF6',
  info: '#5AA6FF',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
  brandGradient: 'linear-gradient(135deg, #1E50D8 0%, #2E6BF6 55%, #5AA6FF 100%)',
  titleGradient: 'linear-gradient(90deg, #EAF1FF, #9EC2FF)',
  cardShadow: '0 6px 20px rgba(46,107,246,0.40)',
  cardHoverShadow: '0 8px 32px rgba(99,102,241,0.20)',
  chart: ['#2563EB', '#2E6BF6', '#22c55e', '#f59e0b', '#ef4444', '#5AA6FF'],
};

const LIGHT: MinderTokens = {
  bg: 'radial-gradient(120% 90% at 15% 0%, #E7EEFF 0%, #F2F5FF 42%, #FBFCFF 100%)',
  surface: '#FFFFFF',
  surfaceAlt: '#F4F7FF',
  border: '#DCE3F5',
  text: '#1E293B',
  textMuted: '#64748B',
  primary: '#2563EB',
  secondary: '#2E6BF6',
  info: '#3B82F6',
  success: '#16A34A',
  warning: '#D97706',
  error: '#DC2626',
  brandGradient: 'linear-gradient(135deg, #1E50D8 0%, #2E6BF6 55%, #5AA6FF 100%)',
  titleGradient: 'linear-gradient(90deg, #1E50D8, #2E6BF6)',
  cardShadow: '0 6px 20px rgba(37,99,235,0.12)',
  cardHoverShadow: '0 10px 32px rgba(37,99,235,0.16)',
  chart: ['#2563EB', '#2E6BF6', '#16A34A', '#D97706', '#DC2626', '#3B82F6'],
};

const TOKENS: Record<MinderTheme, MinderTokens> = { light: LIGHT, dark: DARK };

/** Resolve the token palette for a theme (defaults to dark = the brand sky). */
export function tokensFor(theme: MinderTheme | null | undefined): MinderTokens {
  return theme === 'light' ? LIGHT : DARK;
}

interface ThemeContextValue {
  theme: MinderTheme;
  tokens: MinderTokens;
}

const MinderThemeContext = createContext<ThemeContextValue>({ theme: 'dark', tokens: DARK });

/** Provide the active theme + tokens to a module subtree. */
export function MinderThemeProvider({
  theme,
  children,
}: {
  theme: MinderTheme | null | undefined;
  children: ReactNode;
}) {
  const resolved: MinderTheme = theme === 'light' ? 'light' : 'dark';
  return createElement(
    MinderThemeContext.Provider,
    { value: { theme: resolved, tokens: TOKENS[resolved] } },
    children,
  );
}

/** Read the active theme + design tokens inside a Dashboard subtree. */
export function useMinderTheme(): ThemeContextValue {
  return useContext(MinderThemeContext);
}
