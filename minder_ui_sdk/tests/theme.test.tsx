import { render, screen } from '@testing-library/react';
import { defineDashboard } from '../src/defineDashboard';
import { useMinderTheme, tokensFor } from '../src/theme';

function Probe() {
  const { theme, tokens } = useMinderTheme();
  return <div data-testid="probe">{theme}|{tokens.surface}</div>;
}

const Dash = defineDashboard({
  tabs: [{ id: 'home', label: 'Home' }],
  panels: { home: Probe },
});

// Celesnity Daybreak (light) / Cosmos (dark) surface tokens.
const LIGHT_SURFACE = 'hsl(228 60% 99%)';
const DARK_SURFACE = 'hsl(224 45% 12%)';

it('tokensFor returns the light/dark palette and defaults to dark', () => {
  expect(tokensFor('light').surface).toBe(LIGHT_SURFACE);
  expect(tokensFor('dark').surface).toBe(DARK_SURFACE);
  expect(tokensFor(null).surface).toBe(DARK_SURFACE);
  expect(tokensFor(undefined).surface).toBe(DARK_SURFACE);
});

it('provides the host theme to panels via context', () => {
  render(<Dash apiBase="/api" activeTab="home" theme="light" />);
  expect(screen.getByTestId('probe').textContent).toBe(`light|${LIGHT_SURFACE}`);
});

it('defaults to the dark sky when the host passes no theme', () => {
  render(<Dash apiBase="/api" activeTab="home" />);
  expect(screen.getByTestId('probe').textContent).toBe(`dark|${DARK_SURFACE}`);
});
