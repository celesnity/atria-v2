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

// Celesnity Design System — Cosmos (dark) + Daybreak (light). Values mirror the
// host web-ui CSS variables in web-ui/src/index.css (.cosmos / .daybreak scopes),
// converted to `hsl()` strings so a module renders on-brand with the host.
// Note: Celesnity has no first-class "warning" token (its semantic set is
// success + danger); we keep a distinct amber so status chips stay legible.
const DARK: MinderTokens = {
  bg: 'radial-gradient(120% 140% at 18% 12%, #12245C 0%, #0A1030 45%, #05060F 100%)', // --hero-wash
  surface: 'hsl(224 45% 12%)', // --surface-soft
  surfaceAlt: 'hsl(232 30% 18%)', // --hairline-soft (raised inset)
  border: 'hsl(230 35% 34%)', // --hairline
  text: 'hsl(228 60% 98%)', // --ink
  textMuted: 'hsl(230 24% 66%)', // --text-muted
  primary: 'hsl(221 83% 53%)', // --accent (royal-blue #2563EB)
  secondary: 'hsl(214 90% 58%)', // --accent-2 (azure)
  info: 'hsl(205 92% 60%)', // --accent-magenta
  success: 'hsl(152 55% 55%)', // --semantic-success
  warning: 'hsl(38 92% 58%)', // amber (no Celesnity warning token)
  error: 'hsl(8 80% 62%)', // --semantic-danger
  brandGradient: 'linear-gradient(120deg, #1E50D8 0%, #2E6BF6 50%, #5AA6FF 100%)', // --gradient-brand
  titleGradient: 'linear-gradient(90deg, #EAF1FF, #9EC2FF)',
  cardShadow: '0 6px 20px hsl(221 83% 53% / 0.18)',
  cardHoverShadow: '0 10px 32px hsl(221 83% 53% / 0.26)',
  chart: ['hsl(221 83% 53%)', 'hsl(214 90% 58%)', 'hsl(152 55% 55%)', 'hsl(38 92% 58%)', 'hsl(8 80% 62%)', 'hsl(205 92% 60%)'],
};

const LIGHT: MinderTokens = {
  bg: 'radial-gradient(120% 140% at 18% 12%, hsl(224 40% 95%) 0%, hsl(228 55% 97%) 45%, hsl(228 60% 99%) 100%)',
  surface: 'hsl(228 60% 99%)', // near-white card on lavender wash
  surfaceAlt: 'hsl(224 40% 95%)', // --surface-soft (lavender-mist inset)
  border: 'hsl(250 20% 72%)', // --hairline
  text: 'hsl(230 39% 18%)', // --ink
  textMuted: 'hsl(230 18% 52%)', // --text-muted
  primary: 'hsl(221 83% 50%)', // --accent
  secondary: 'hsl(214 90% 55%)', // --accent-2
  info: 'hsl(205 90% 58%)', // --accent-magenta
  success: 'hsl(152 60% 32%)', // --semantic-success
  warning: 'hsl(35 92% 45%)', // amber (no Celesnity warning token)
  error: 'hsl(0 70% 45%)', // --semantic-danger
  brandGradient: 'linear-gradient(120deg, #1E50D8 0%, #2E6BF6 50%, #5AA6FF 100%)', // --gradient-brand
  titleGradient: 'linear-gradient(90deg, #1E50D8, #2E6BF6)',
  cardShadow: '0 6px 20px hsl(230 39% 18% / 0.08)',
  cardHoverShadow: '0 10px 32px hsl(230 39% 18% / 0.12)',
  chart: ['hsl(221 83% 50%)', 'hsl(214 90% 55%)', 'hsl(152 60% 32%)', 'hsl(35 92% 45%)', 'hsl(0 70% 45%)', 'hsl(205 90% 58%)'],
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
