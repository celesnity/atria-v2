import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, RotateCw } from 'lucide-react';
import { useChatStore } from '../../stores/chat';
import { useModulesStore } from '../../stores/modules';
import type { ModuleTab } from '../../stores/modules';
import { useModuleBridge } from './useModuleBridge';
import { RemoteDashboard } from './RemoteDashboard';

/** Resolve the iframe URL for a module tab: entry file, hash mode, or base. */
export function moduleTabSrc(moduleName: string, tab: ModuleTab | null): string {
  const base = `/api/modules/${encodeURIComponent(moduleName)}`;
  if (tab?.entry) return `${base}/${tab.entry.replace(/^\/+/, '')}`;
  if (tab) return `${base}/dashboard.html#${tab.id}`;
  return `${base}/dashboard.html`;
}

interface ModuleDashboardViewProps {
  moduleName: string;
}

/**
 * Renders a module's interactive dashboard.html inside a sandboxed iframe,
 * wrapped with a thin header that allows returning to chat or reloading.
 *
 * The actual host <-> iframe protocol is handled by `useModuleBridge`.
 */
export function ModuleDashboardView({ moduleName }: ModuleDashboardViewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const closeDashboard = useModulesStore((s) => s.closeDashboard);
  const summary = useModulesStore((s) =>
    s.modulesWithDashboards.find((m) => m.name === moduleName) ?? null,
  );
  const activeTabId = useModulesStore((s) => s.activeModuleTab);
  const activeTab = summary?.tabs.find((t) => t.id === activeTabId) ?? null;

  const manifestTitle = summary?.dashboard_title ?? `${moduleName} · dashboard`;
  const [title, setTitle] = useState<string>(manifestTitle);

  // Reset title when switching modules or when manifest changes.
  useEffect(() => {
    setTitle(manifestTitle);
  }, [manifestTitle]);

  // Listen for in-iframe title updates dispatched by the bridge.
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ module: string; text: string }>).detail;
      if (!detail || detail.module !== moduleName) return;
      if (typeof detail.text === 'string' && detail.text.length > 0) {
        setTitle(detail.text);
      }
    };
    window.addEventListener('minder:module:title', handler as EventListener);
    return () =>
      window.removeEventListener('minder:module:title', handler as EventListener);
  }, [moduleName]);

  useModuleBridge({
    moduleName,
    sessionId: currentSessionId,
    iframeRef,
    visible: true,
  });

  const handleRefresh = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    // Reassigning src forces a fresh load while preserving the bridge listeners.
    iframe.src = iframe.src;
  };

  const iframeSrc = moduleTabSrc(moduleName, activeTab);

  if (summary?.remote) {
    return (
      <div className="flex h-full w-full flex-col bg-bg-000">
        <div className="flex-1 min-h-0 overflow-auto">
          <RemoteDashboard summary={summary as any} activeTab={activeTabId} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col bg-bg-000">
      <iframe
        ref={iframeRef}
        sandbox="allow-scripts allow-forms"
        src={iframeSrc}
        title={`${moduleName} dashboard`}
        className="flex-1 border-0 bg-bg-000"
      />
    </div>
  );
}

export default ModuleDashboardView;
