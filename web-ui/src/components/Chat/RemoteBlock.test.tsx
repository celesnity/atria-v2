// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('../../lib/federation', () => ({
  registerRemote: vi.fn(),
  loadRemoteComponent: vi.fn(async () =>
    ({ answer, apiBase }: { answer: string; apiBase: string }) => <div>block-ok:{answer}:{apiBase}</div>),
}));

import { RemoteBlock } from './RemoteBlock';

describe('RemoteBlock', () => {
  it('registers the remote and renders the loaded component with props + apiBase', async () => {
    const fed = await import('../../lib/federation');
    render(<RemoteBlock
      remoteName="maintenance_copilot"
      remoteEntry="http://localhost:9200/dashboard/remoteEntry.js"
      component="./MaintenanceAnswer"
      props={{ answer: 'hi' }}
      apiBase="http://localhost:9200"
    />);
    await waitFor(() =>
      expect(screen.getByText(/block-ok:hi:http:\/\/localhost:9200/)).toBeTruthy());
    expect(fed.registerRemote).toHaveBeenCalledWith({
      name: 'maintenance_copilot',
      entry: 'http://localhost:9200/dashboard/remoteEntry.js',
    });
  });
});
