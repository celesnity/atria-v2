import { ProjectSidebar } from './ProjectSidebar';
import { ChatInterface } from '../Chat/ChatInterface';
import { useChatStore } from '../../stores/chat';

/**
 * ChatRail — the left column. Stacks the session/project navigation
 * (ProjectSidebar) above the active conversation (ChatInterface). When the
 * rail is collapsed, ProjectSidebar renders its thin-strip form and the
 * conversation is hidden to give the module center full width.
 */
export function ChatRail() {
  const collapsed = useChatStore((s) => s.sidebarCollapsed);
  return (
    <div className="flex h-full min-h-0">
      <ProjectSidebar />
      {!collapsed && (
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden border-r border-hairline-soft/25">
          <ChatInterface />
        </div>
      )}
    </div>
  );
}
