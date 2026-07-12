// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../lib/federation', () => ({
  registerRemote: vi.fn(),
  loadRemoteComponent: vi.fn(async () =>
    ({ apiBase }: { apiBase: string }) => <div>remote-ok:{apiBase}</div>),
}));

import { RemoteDashboard } from './RemoteDashboard';

describe('RemoteDashboard', () => {
  it('registers the remote and renders the loaded component with apiBase', async () => {
    const fed = await import('../../lib/federation');
    render(<RemoteDashboard summary={{
      name: 'maintenance_copilot', remote: true, remote_name: 'maintenance_copilot',
      remote_entry: 'http://localhost:9200/dashboard/remoteEntry.js',
      remote_dashboard: './Dashboard', api_base: 'http://localhost:9200',
    } as any} />);
    await waitFor(() =>
      expect(screen.getByText(/remote-ok:http:\/\/localhost:9200/)).toBeTruthy());
    expect(fed.registerRemote).toHaveBeenCalledWith({
      name: 'maintenance_copilot',
      entry: 'http://localhost:9200/dashboard/remoteEntry.js',
    });
  });
});
