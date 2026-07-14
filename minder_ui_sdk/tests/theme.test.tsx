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

it('tokensFor returns the light/dark palette and defaults to dark', () => {
  expect(tokensFor('light').surface).toBe('#FFFFFF');
  expect(tokensFor('dark').surface).toBe('#111A2E');
  expect(tokensFor(null).surface).toBe('#111A2E');
  expect(tokensFor(undefined).surface).toBe('#111A2E');
});

it('provides the host theme to panels via context', () => {
  render(<Dash apiBase="/api" activeTab="home" theme="light" />);
  expect(screen.getByTestId('probe').textContent).toBe('light|#FFFFFF');
});

it('defaults to the dark sky when the host passes no theme', () => {
  render(<Dash apiBase="/api" activeTab="home" />);
  expect(screen.getByTestId('probe').textContent).toBe('dark|#111A2E');
});
