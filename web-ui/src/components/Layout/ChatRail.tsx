import { ProjectSidebar } from './ProjectSidebar';

/**
 * ChatRail — the left column. It is a single narrow rail: ProjectSidebar stacks
 * the workspace header, new-chat action, the session dropdown, and the active
 * conversation (ChatInterface) vertically within one resizable column, so the
 * center is free for the module UI. When collapsed, ProjectSidebar renders its
 * thin-strip form.
 */
export function ChatRail() {
  return <ProjectSidebar />;
}
