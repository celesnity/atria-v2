import { useState, useEffect, useCallback } from 'react';
import { useMediaQuery } from 'usehooks-ts';
import { ProjectSidebar } from '../components/Layout/ProjectSidebar';
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

  const openStatusDialog = useCallback(() => setStatusDialogOpen(true), []);
  const closeStatusDialog = useCallback(() => setStatusDialogOpen(false), []);

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

  const centerContent = activeModuleDashboard ? (
    <ModuleDashboardView moduleName={activeModuleDashboard} />
  ) : (
    <ChatInterface />
  );

  // ── Phone layout: drawer sidebar + single panel + bottom tab bar ──
  if (isPhone) {
    // Files/Editor only make sense with a live conversation; otherwise show chat.
    const panel: MobilePanel = currentSessionId ? mobilePanel : 'chat';
    return (
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden bg-bg-000">
        {/* Drawer (fixed/off-canvas — does not take layout space) */}
        <ProjectSidebar />

        <main className="flex-1 min-h-0 flex flex-col overflow-hidden bg-bg-000">
          {panel === 'chat' && centerContent}
          {panel === 'files' && <ExplorerPane />}
          {panel === 'editor' && <EditorPane />}
        </main>

        <MobileTabBar active={panel} onChange={setMobilePanel} />
        {dialogs}
      </div>
    );
  }

  // ── Desktop / tablet: three coexisting columns ──
  return (
    <div className="flex-1 min-h-0 flex overflow-hidden bg-bg-000">
      <ProjectSidebar />
      <main className="flex-1 flex flex-col overflow-hidden bg-bg-000">
        {centerContent}
      </main>
      <ArtifactViewer />
      {dialogs}
    </div>
  );
}
