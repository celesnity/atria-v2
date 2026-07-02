import { PanelRightOpen } from 'lucide-react';
import { useChatStore } from '../../stores/chat';
import { useViewerTabsStore } from '../../stores/viewerTabs';
import { TabBar } from './TabBar';
import { FileTree } from './FileTree';
import { ViewerDispatcher } from './viewers';
import { LeftPaneTabs, useLeftMode } from './LeftPaneTabs';
import { ModuleGallery } from './ModuleGallery';

/**
 * Shared Explorer/Editor panes.
 *
 * These are the two halves of the artifact panel, factored out so the mobile
 * bottom-tab layout (one panel at a time) can mount the file explorer and the
 * editor directly — without the desktop panel's resize chrome. The desktop
 * ArtifactViewer keeps its own composition; these are the phone-facing views.
 */

/** File explorer: [Files | Modules] tabs + the tree / module gallery. */
export function ExplorerPane() {
  const currentSessionId = useChatStore(s => s.currentSessionId);
  const [leftMode, setLeftMode] = useLeftMode();
  const convInt = currentSessionId ? parseInt(currentSessionId, 10) : NaN;
  if (!currentSessionId || Number.isNaN(convInt)) {
    return <PaneEmpty label="No conversation open" />;
  }
  return (
    <div className="flex flex-col h-full min-h-0 bg-bg-100">
      <LeftPaneTabs mode={leftMode} onChange={setLeftMode} />
      <div className="flex-1 min-h-0 overflow-hidden">
        {leftMode === 'files' ? (
          <FileTree
            convId={currentSessionId}
            scope={{ kind: 'conv', id: convInt }}
            autoExpand={['.artifacts']}
          />
        ) : (
          <ModuleGallery convId={currentSessionId} />
        )}
      </div>
    </div>
  );
}

/** Editor: open-file tab bar + the active viewer (or an empty state). */
export function EditorPane() {
  const currentSessionId = useChatStore(s => s.currentSessionId);
  const activeTab = useViewerTabsStore(s => {
    if (!currentSessionId) return null;
    const slice = s.tabsByConv[currentSessionId];
    if (!slice) return null;
    return slice.tabs.find(t => t.id === slice.activeId) ?? null;
  });
  const convInt = currentSessionId ? parseInt(currentSessionId, 10) : NaN;
  if (!currentSessionId || Number.isNaN(convInt)) {
    return <PaneEmpty label="No conversation open" />;
  }
  return (
    <div className="flex flex-col h-full min-h-0 bg-canvas">
      <div className="flex items-center border-b border-hairline-soft/60 bg-surface-soft/30 flex-shrink-0 min-w-0">
        <TabBar convId={currentSessionId} />
      </div>
      <div className="flex-1 min-w-0 min-h-0">
        {activeTab ? (
          <ViewerDispatcher convId={convInt} tab={activeTab} />
        ) : (
          <PaneEmpty label="Select a file to preview" icon />
        )}
      </div>
    </div>
  );
}

function PaneEmpty({ label, icon }: { label: string; icon?: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-2 select-none">
      {icon && (
        <div className="w-10 h-10 rounded-full border border-hairline flex items-center justify-center text-ink/20">
          <PanelRightOpen className="w-4 h-4" />
        </div>
      )}
      <p className="text-[12px] font-mono text-ink/35">{label}</p>
    </div>
  );
}
