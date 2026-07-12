import { useEffect, useState, type ComponentType } from 'react';
import { registerRemote, loadRemoteComponent } from '../../lib/federation';

interface RemoteSummary {
  name: string;
  remote?: boolean;
  remote_name?: string | null;
  remote_entry?: string | null;
  remote_dashboard?: string | null;
  api_base?: string | null;
}

/**
 * Loads a service-module's federated dashboard remote and renders it natively
 * in-host (no iframe), sharing the host's React. The remote receives `apiBase`
 * so its own fetches hit the module's connector directly.
 */
export function RemoteDashboard({ summary }: { summary: RemoteSummary }) {
  const [Comp, setComp] = useState<ComponentType<any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (!summary.remote_name || !summary.remote_entry || !summary.remote_dashboard) {
      setError('module is missing federation remote fields');
      return;
    }
    registerRemote({ name: summary.remote_name, entry: summary.remote_entry });
    loadRemoteComponent(summary.remote_name, summary.remote_dashboard)
      .then((c) => { if (alive) setComp(() => c); })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [summary.remote_name, summary.remote_entry, summary.remote_dashboard]);

  if (error) return <div className="p-4 text-sm text-semantic-danger">Dashboard failed: {error}</div>;
  if (!Comp) return <div className="p-4 text-sm text-text-300">Loading dashboard…</div>;
  return <Comp apiBase={summary.api_base ?? ''} />;
}
