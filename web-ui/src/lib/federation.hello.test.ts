import { describe, it, expect, vi, beforeEach } from 'vitest';

const registerRemotes = vi.fn();
const loadRemote = vi.fn();
vi.mock('@module-federation/runtime', () => ({
  registerRemotes: (...a: unknown[]) => registerRemotes(...a),
  loadRemote: (...a: unknown[]) => loadRemote(...a),
  init: vi.fn(),
}));

describe('federation helper', () => {
  beforeEach(() => { registerRemotes.mockClear(); loadRemote.mockClear(); });

  it('registers a remote by name+entry', async () => {
    const { registerRemote } = await import('./federation');
    registerRemote({ name: 'maintenance_copilot', entry: 'http://localhost:9200/dashboard/remoteEntry.js' });
    expect(registerRemotes).toHaveBeenCalledWith(
      [{ name: 'maintenance_copilot', entry: 'http://localhost:9200/dashboard/remoteEntry.js' }],
      { force: true },
    );
  });

  it('loads an exposed component and returns its default export', async () => {
    const Dummy = () => null;
    loadRemote.mockResolvedValue({ default: Dummy });
    const { loadRemoteComponent } = await import('./federation');
    const Comp = await loadRemoteComponent('maintenance_copilot', './Dashboard');
    expect(loadRemote).toHaveBeenCalledWith('maintenance_copilot/Dashboard');
    expect(Comp).toBe(Dummy);
  });
});
