import { useState, useEffect, useCallback, useRef } from 'react';
import { useMediaQuery } from 'usehooks-ts';
import { ProjectSidebar } from '../components/Layout/ProjectSidebar';
import { ChatRail } from '../components/Layout/ChatRail';
import { ChatInterface } from '../components/Chat/ChatInterface';
import { ApprovalDialog } from '../components/ApprovalDialog';
import { AskUserDialog } from '../components/Chat/AskUserDialog';
import { PlanApprovalDialog } from '../components/Chat/PlanApprovalDialog';
import { CommandPalette } from '../components/Chat/CommandPalette';
import { StatusDialog } from '../components/Chat/StatusDialog';
import { ArtifactViewer } from '../components/ArtifactViewer/ArtifactViewer';
import { ExplorerPane, EditorPane } from '../components/ArtifactViewer/panes';
import { MobileTabBar, type MobilePanel } from '../components/Layout/MobileTabBar';
import { useChatStore } from '../stores/chat';
import { useViewerTabsStore } from '../stores/viewerTabs';
import { useModulesStore } from '../stores/modules';
import { ModuleDashboardView } from '../components/ModuleDashboard/ModuleDashboardView';

export function ChatPage() {
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);

  const commandPaletteOpen = useChatStore(state => state.commandPaletteOpen);
  const closeCommandPalette = useChatStore(state => state.closeCommandPalette);
  const currentSessionId = useChatStore(state => state.currentSessionId);
  const activeModuleDashboard = useModulesStore(s => s.activeModuleDashboard);
  const modulesWithDashboards = useModulesStore(s => s.modulesWithDashboards);
  const openDashboard = useModulesStore(s => s.openDashboard);

  const openStatusDialog = useCallback(() => setStatusDialogOpen(true), []);
  const closeStatusDialog = useCallback(() => setStatusDialogOpen(false), []);

  // Chat-first → module-workspace transition: when a conversation becomes active
  // (the user opened or started a chat) and no module is open yet, auto-open the
  // first available module so the center isn't empty. Tracked per session so
  // manually closing a module later doesn't immediately reopen it. Retries once
  // the module list finishes loading (deps include modulesWithDashboards).
  const autoModuleSession = useRef<string | null>(null);
  useEffect(() => {
    if (!currentSessionId) {
      autoModuleSession.current = null;
      return;
    }
    if (currentSessionId === autoModuleSession.current) return;
    if (activeModuleDashboard) {
      autoModuleSession.current = currentSessionId;
      return;
    }
    if (modulesWithDashboards.length > 0) {
      openDashboard(modulesWithDashboards[0].name);
      autoModuleSession.current = currentSessionId;
    }
  }, [currentSessionId, activeModuleDashboard, modulesWithDashboards, openDashboard]);

  // Phone: one panel at a time, switched by the bottom tab bar.
  const isPhone = useMediaQuery('(max-width: 767px)');
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>('chat');

  // Opening a file (active editor tab changes) jumps to the Editor panel on phones.
  const activeTabId = useViewerTabsStore(s => {
    if (!currentSessionId) return null;
    return s.tabsByConv[currentSessionId]?.activeId ?? null;
  });
  useEffect(() => {
    if (isPhone && activeTabId) setMobilePanel('editor');
  }, [isPhone, activeTabId]);

  const dialogs = (
    <>
      <ApprovalDialog />
      <AskUserDialog />
      <PlanApprovalDialog />
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={closeCommandPalette}
        onOpenStatus={openStatusDialog}
      />
      <StatusDialog isOpen={statusDialogOpen} onClose={closeStatusDialog} />
    </>
  );

  // The center column shows the active module's UI, or an empty-state prompt.
  // Chat is no longer a center fallback — it lives permanently in the left rail.
  const centerContent = activeModuleDashboard ? (
    <ModuleDashboardView moduleName={activeModuleDashboard} />
  ) : (
    <div className="flex flex-1 items-center justify-center p-8 text-center">
      <div className="max-w-sm">
        <p className="text-sm text-text-secondary">
          Pick a module from the breadcrumb above, or keep chatting in the left rail.
        </p>
      </div>
    </div>
  );

  // ── Phone layout: drawer sidebar + single panel + bottom tab bar ──
  if (isPhone) {
    // Files/Editor only make sense with a live conversation; Chat and Module
    // stand on their own, so fall back to chat only for the file-bound panels.
    const panel: MobilePanel =
      currentSessionId || mobilePanel === 'chat' || mobilePanel === 'module'
        ? mobilePanel
        : 'chat';
    return (
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-bg-000">
        {/* Drawer (fixed/off-canvas — does not take layout space) */}
        <ProjectSidebar />

        <main className="flex-1 min-h-0 flex flex-col overflow-hidden bg-bg-000">
          {panel === 'chat' && <ChatInterface />}
          {panel === 'module' && centerContent}
          {panel === 'files' && <ExplorerPane />}
          {panel === 'editor' && <EditorPane />}
        </main>

        <MobileTabBar active={panel} onChange={setMobilePanel} />
        {dialogs}
      </div>
    );
  }

  // ── Desktop / tablet, chat-first empty state: no conversation yet → a single
  // full-width chat screen (the redesigned LandingPage). No rail, module, or
  // artifact panel until a chat is opened. ──
  if (!currentSessionId) {
    return (
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-bg-000">
        <main className="flex-1 min-h-0 flex flex-col overflow-hidden bg-bg-000">
          <ChatInterface />
        </main>
        {dialogs}
      </div>
    );
  }

  // ── Desktop / tablet, active conversation: chat shifts into the left rail and
  // a module opens in the center (auto-selected above). Artifacts on the right. ──
  return (
    <div className="flex-1 min-h-0 flex overflow-hidden bg-bg-000">
      <ChatRail />
      <main className="flex-1 flex flex-col overflow-hidden bg-bg-000 min-w-0">
        {centerContent}
      </main>
      <ArtifactViewer />
      {dialogs}
    </div>
  );
}
