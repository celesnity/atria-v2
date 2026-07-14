import { useRef } from 'react';
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
 * Renders a module's dashboard in the center pane — a federated remote in-host,
 * or the module's `dashboard.html` inside a sandboxed iframe. There is no local
 * chrome: the top bar owns the breadcrumb + tabs, and the chat rail is the way
 * back to a conversation. The host <-> iframe protocol lives in `useModuleBridge`.
 */
export function ModuleDashboardView({ moduleName }: ModuleDashboardViewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const summary = useModulesStore((s) =>
    s.modulesWithDashboards.find((m) => m.name === moduleName) ?? null,
  );
  const activeTabId = useModulesStore((s) => s.activeModuleTab);
  const activeTab = summary?.tabs.find((t) => t.id === activeTabId) ?? null;

  useModuleBridge({
    moduleName,
    sessionId: currentSessionId,
    iframeRef,
    visible: true,
  });

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
