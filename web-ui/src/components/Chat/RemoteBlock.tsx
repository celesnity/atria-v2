import { useEffect, useState, type ComponentType } from 'react';
import { registerRemote, loadRemoteComponent } from '../../lib/federation';

interface RemoteBlockProps {
  remoteName: string;
  remoteEntry: string;
  component: string;
  props?: Record<string, any>;
  apiBase?: string;
}

/**
 * Loads a service-module's federated chat-block remote and renders it natively
 * in-host (no iframe), sharing the host's React. The block component receives its
 * `props` plus `apiBase` so it can call its own connector directly.
 */
export function RemoteBlock({ remoteName, remoteEntry, component, props = {}, apiBase = '' }: RemoteBlockProps) {
  const [Comp, setComp] = useState<ComponentType<any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (!remoteName || !remoteEntry || !component) {
      setError('block is missing federation fields');
      return;
    }
    registerRemote({ name: remoteName, entry: remoteEntry });
    loadRemoteComponent(remoteName, component)
      .then((c) => { if (alive) setComp(() => c); })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [remoteName, remoteEntry, component]);

  if (error) return <div className="p-4 text-sm text-red-400">Block failed: {error}</div>;
  if (!Comp) return <div className="p-4 text-sm text-text-300">Loading…</div>;
  return <Comp {...props} apiBase={apiBase} />;
}
