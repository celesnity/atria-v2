// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RemoteDashboard } from './RemoteDashboard';

vi.mock('../../lib/federation', () => ({
  registerRemote: vi.fn(),
  loadRemoteComponent: vi.fn(() =>
    Promise.resolve((props: { apiBase: string; activeTab?: string | null }) => (
      <div data-testid="remote">
        {props.apiBase}|{props.activeTab ?? 'none'}
      </div>
    )),
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
  it('passes apiBase and activeTab to the federated component', async () => {
    render(<RemoteDashboard summary={summary} activeTab="media" />);
    await waitFor(() => expect(screen.getByTestId('remote')).toBeTruthy());
    expect(screen.getByTestId('remote').textContent).toBe('http://x|media');
  });
});
