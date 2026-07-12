// @vitest-environment jsdom
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { RemoteDashboard } from './RemoteDashboard';

afterEach(cleanup);

// The real theme store reads window.localStorage at module init (fine in a real
// browser, absent in this jsdom env). Mock it and drive the sky from a variable.
let mockSky: 'cosmos' | 'daybreak' = 'cosmos';
vi.mock('../../stores/theme', () => ({
  useThemeStore: (selector: (s: { theme: 'cosmos' | 'daybreak' }) => unknown) =>
    selector({ theme: mockSky }),
}));

vi.mock('../../lib/federation', () => ({
  registerRemote: vi.fn(),
  loadRemoteComponent: vi.fn(() =>
    Promise.resolve(
      (props: { apiBase: string; activeTab?: string | null; theme?: string }) => (
        <div data-testid="remote">
          {props.apiBase}|{props.activeTab ?? 'none'}|{props.theme ?? 'none'}
        </div>
      ),
    ),
  ),
}));

const summary = {
  name: 'm',
  remote: true,
  remote_name: 'm',
  remote_entry: 'http://x/dashboard/remoteEntry.js',
  remote_dashboard: './Dashboard',
  api_base: 'http://x',
};

describe('RemoteDashboard', () => {
  it('passes apiBase, activeTab, and the cosmos sky as dark', async () => {
    mockSky = 'cosmos';
    render(<RemoteDashboard summary={summary} activeTab="media" />);
    await waitFor(() => expect(screen.getByTestId('remote')).toBeTruthy());
    expect(screen.getByTestId('remote').textContent).toBe('http://x|media|dark');
  });

  it('maps the daybreak sky to light', async () => {
    mockSky = 'daybreak';
    render(<RemoteDashboard summary={summary} activeTab="jobs" />);
    await waitFor(() => expect(screen.getByTestId('remote')).toBeTruthy());
    expect(screen.getByTestId('remote').textContent).toBe('http://x|jobs|light');
  });
});
