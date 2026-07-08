import {
  Check,
  ChevronDown,
  ChevronRight,
  Folder,
  MessageSquare,
  Package,
  Plus,
  Settings,
  Trash2,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useLocalStorage, useMediaQuery } from "usehooks-ts";
import { ResizeHandle } from "../ui/ResizeHandle";
import { useChatStore } from "../../stores/chat";
import { useModulesStore } from "../../stores/modules";
import { useProjectsStore } from "../../stores/projects";
import type { Project } from "../../types";
import { SettingsModal } from "../Settings/SettingsModal";
import { CreateConversationModal } from "./CreateConversationModal";
import { CreateProjectModal } from "./CreateProjectModal";

/** Short relative time, e.g. "Just now", "5m ago", "3h ago", "2d ago", or a date. */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

/** Signature brand mark — a small gradient-brand tile with a soft nebula glow. */
function BrandMark({ size = "md" }: { size?: "sm" | "md" }) {
  const dim = size === "sm" ? "h-6 w-6" : "h-7 w-7";
  return (
    <span
      className={`relative grid ${dim} flex-shrink-0 place-items-center rounded-md bg-gradient-brand shadow-glow-accent`}
    >
      <span className="h-2 w-2 rounded-md bg-white/95 shadow-[0_0_8px_rgba(255,255,255,0.6)]" />
    </span>
  );
}

/** A tiny uppercase section eyebrow with a trailing hairline rule. */
function SectionEyebrow({
  label,
  meta,
  action,
}: {
  label: string;
  meta?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 px-3 pb-2">
      <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-text-muted">
        {label}
      </span>
      {meta && (
        <span
          className="min-w-0 flex-1 truncate text-[10px] font-mono text-text-muted/70"
          title={meta}
        >
          {meta}
        </span>
      )}
      <span className={meta ? "" : "flex-1"} />
      <span className="h-px flex-1 bg-hairline-soft/40" aria-hidden />
      {action}
    </div>
  );
}

export function ProjectSidebar() {
  const {
    projects,
    conversations,
    isLoading,
    loadProjects,
    loadConversations,
    deleteProject,
    deleteConversation,
    createConversation,
  } = useProjectsStore();
  const workspaceProjectId = useProjectsStore((s) => s.workspaceProjectId);

  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const loadSession = useChatStore((s) => s.loadSession);
  const isCollapsed = useChatStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useChatStore((s) => s.toggleSidebar);

  // Below md the sidebar becomes an off-canvas drawer instead of a static column.
  const isMobile = useMediaQuery("(max-width: 767px)");
  const mobileSidebarOpen = useChatStore((s) => s.mobileSidebarOpen);
  const closeMobileSidebar = useChatStore((s) => s.closeMobileSidebar);

  const modulesWithDashboards = useModulesStore((s) => s.modulesWithDashboards);
  const activeModuleDashboard = useModulesStore((s) => s.activeModuleDashboard);
  const openModuleDashboard = useModulesStore((s) => s.openDashboard);
  const closeModuleDashboard = useModulesStore((s) => s.closeDashboard);
  const refreshModules = useModulesStore((s) => s.refresh);

  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [createConvFor, setCreateConvFor] = useState<Project | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<{
    type: "project" | "conv";
    id: string;
    projectId?: string;
  } | null>(null);
  const [creatingChat, setCreatingChat] = useState(false);
  // Persisted, drag-to-resize width for the desktop sidebar column.
  const [sidebarWidth, setSidebarWidth] = useLocalStorage<number>(
    "sidebar.width",
    256,
  );

  // Project switcher: which project's conversations are shown in the flat CHATS list.
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const switcherRef = useRef<HTMLDivElement>(null);

  const reduce = useReducedMotion();

  useEffect(() => {
    loadProjects();
    refreshModules();
  }, []);

  // Default the active project to the user's workspace project once it loads.
  useEffect(() => {
    if (!activeProjectId && workspaceProjectId) {
      setActiveProjectId(workspaceProjectId);
      loadConversations(workspaceProjectId);
    }
  }, [workspaceProjectId, activeProjectId]);

  // Follow the open conversation: when a session is opened that lives in a
  // different project (e.g. a Minder chat surfaced via the module dashboard),
  // switch the sidebar to that project so the chat is visible/highlighted.
  useEffect(() => {
    if (!currentSessionId) return;
    for (const [pid, convs] of Object.entries(conversations)) {
      if (pid !== activeProjectId && convs.some((c) => c.id === currentSessionId)) {
        setActiveProjectId(pid);
        break;
      }
    }
  }, [currentSessionId, conversations, activeProjectId]);

  // Close the switcher dropdown on outside click.
  useEffect(() => {
    if (!switcherOpen) return;
    const onClick = (e: MouseEvent) => {
      if (switcherRef.current && !switcherRef.current.contains(e.target as Node)) {
        setSwitcherOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [switcherOpen]);

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  const activeConversations = activeProjectId
    ? conversations[activeProjectId] ?? []
    : [];
  // The workspace project's name is a long filesystem path; show a friendly label instead.
  const activeProjectLabel =
    activeProjectId && activeProjectId === workspaceProjectId
      ? "Workspace"
      : activeProject?.name ?? "";

  const selectProject = (projectId: string) => {
    setActiveProjectId(projectId);
    setSwitcherOpen(false);
    loadConversations(projectId);
  };

  const handleNewChat = async () => {
    const pid = activeProjectId || workspaceProjectId;
    if (creatingChat || !pid) return;
    setCreatingChat(true);
    try {
      // createConversation loads the new session automatically.
      await createConversation(pid, "New Chat");
      closeModuleDashboard();
      closeMobileSidebar();
    } finally {
      setCreatingChat(false);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!confirmDelete) return;
    if (confirmDelete.type === "project") {
      await deleteProject(confirmDelete.id);
    } else if (confirmDelete.projectId) {
      await deleteConversation(confirmDelete.projectId, confirmDelete.id);
    }
    setConfirmDelete(null);
  };

  if (isCollapsed && !isMobile) {
    return (
      <aside
        data-surface="dark"
        className="relative flex w-14 flex-col items-center gap-3 border-r border-hairline-soft/25 bg-bg-100 py-4"
      >
        {/* Ambient accent wash bleeding down from the top of the rail. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-40 opacity-70"
          style={{
            background:
              "radial-gradient(120% 90% at 50% 0%, hsl(232 74% 53% / 0.18), transparent 72%)",
          }}
        />
        <button
          onClick={toggleSidebar}
          className="relative grid h-8 w-8 place-items-center rounded-md text-text-muted transition-colors hover:bg-surface-soft hover:text-ink"
          title="Expand sidebar"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        <button
          onClick={() => {
            toggleSidebar();
            setCreateProjectOpen(true);
          }}
          className="relative grid h-9 w-9 place-items-center rounded-md bg-gradient-brand text-white shadow-glow-accent transition-transform duration-base ease-motion-spring hover:scale-105"
          title="New project"
        >
          <Plus className="h-4 w-4" />
        </button>
        {modulesWithDashboards.length > 0 && (
          <div className="my-1 h-px w-7 bg-hairline-soft/30" />
        )}
        {modulesWithDashboards.map((m) => {
          const isActive = activeModuleDashboard === m.name;
          return (
            <button
              key={m.name}
              onClick={() =>
                isActive ? closeModuleDashboard() : openModuleDashboard(m.name)
              }
              className={`relative grid h-8 w-8 place-items-center rounded-md transition-colors ${
                isActive
                  ? "bg-accent-cobalt/15 text-accent-cobalt ring-1 ring-accent-cobalt/30"
                  : "text-text-muted hover:bg-surface-soft hover:text-ink"
              }`}
              title={m.tooltip}
              aria-label={m.display_name}
            >
              {m.icon_url ? (
                <img src={m.icon_url} className="h-4 w-4" alt="" />
              ) : (
                <Package className="h-4 w-4" />
              )}
            </button>
          );
        })}
      </aside>
    );
  }

  const sidebarBody = (
    <>
      {/* Ambient nebula wash — gives the panel depth instead of a flat fill. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-56 opacity-70"
        style={{
          background:
            "radial-gradient(130% 80% at 18% 0%, hsl(232 74% 53% / 0.16), transparent 62%), radial-gradient(120% 70% at 92% 4%, hsl(286 58% 56% / 0.12), transparent 60%)",
        }}
      />

      {/* Brand header: identity on the left, project + settings controls on the right. */}
      <div className="relative flex items-center gap-2 px-3 py-3">
        <button
          onClick={() => (isMobile ? closeMobileSidebar() : toggleSidebar())}
          className="group flex min-w-0 items-center gap-2.5 text-left"
          title="Collapse sidebar"
        >
          <BrandMark />
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold leading-tight tracking-tight text-ink">
              Workspace
            </span>
            <span className="flex items-center gap-1 text-[10px] font-mono text-text-muted transition-colors group-hover:text-text-secondary">
              <ChevronRight className="h-2.5 w-2.5 rotate-180" />
              Collapse
            </span>
          </span>
        </button>

        <div className="ml-auto flex items-center gap-1">
          {/* Project switcher — pick which project's chats are listed */}
          <div className="relative" ref={switcherRef}>
            <button
              onClick={() => setSwitcherOpen((o) => !o)}
              className="flex items-center gap-0.5 rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-soft hover:text-ink focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cobalt"
              title="Switch project"
              aria-label="Switch project"
              aria-haspopup="menu"
              aria-expanded={switcherOpen}
            >
              <Folder className="h-4 w-4" />
              <ChevronDown
                className={`h-3 w-3 transition-transform duration-base ${switcherOpen ? "rotate-180" : ""}`}
              />
            </button>
            {switcherOpen && (
              <motion.div
                role="menu"
                initial={reduce ? false : { opacity: 0, y: -6, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                className="absolute right-0 top-full z-50 mt-2 max-h-72 w-60 overflow-y-auto rounded-md border border-hairline-soft/40 bg-bg-000/95 py-1.5 shadow-modal backdrop-blur-xl"
              >
                <div className="px-3 pb-1 pt-0.5 text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-text-muted">
                  Projects
                </div>
                {projects.map((project) => {
                  const isActive = project.id === activeProjectId;
                  return (
                    <div
                      key={project.id}
                      className="group mx-1 flex items-center gap-1.5 rounded-md px-2 py-1.5 hover:bg-surface-soft/70"
                    >
                      <button
                        role="menuitemradio"
                        aria-checked={isActive}
                        onClick={() => selectProject(project.id)}
                        className="flex min-w-0 flex-1 items-center gap-2 text-left focus:outline-none"
                      >
                        {isActive ? (
                          <Check className="h-3.5 w-3.5 flex-shrink-0 text-accent-cobalt" />
                        ) : (
                          <Folder className="h-3.5 w-3.5 flex-shrink-0 text-text-muted" />
                        )}
                        <span
                          className={`flex-1 truncate text-xs ${isActive ? "font-medium text-ink" : "text-text-secondary"}`}
                        >
                          {project.name}
                        </span>
                      </button>
                      <button
                        onClick={() =>
                          setConfirmDelete({ type: "project", id: project.id })
                        }
                        className="rounded p-0.5 text-text-muted opacity-0 transition-colors hover:bg-surface-soft hover:text-semantic-danger focus:outline-none focus-visible:ring-1 focus-visible:ring-semantic-danger group-hover:opacity-100"
                        title="Delete project"
                        aria-label={`Delete project ${project.name}`}
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    </div>
                  );
                })}
                <div className="mx-1 mt-1 border-t border-hairline-soft/30 pt-1">
                  <button
                    onClick={() => {
                      setSwitcherOpen(false);
                      setCreateProjectOpen(true);
                    }}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 font-mono text-xs text-text-secondary transition-colors hover:bg-surface-soft/70 hover:text-accent-cobalt focus:outline-none"
                    role="menuitem"
                  >
                    <Plus className="h-3 w-3" />
                    New project
                  </button>
                </div>
              </motion.div>
            )}
          </div>
          <button
            onClick={() => setSettingsOpen(true)}
            className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface-soft hover:text-ink"
            title="Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Primary action — promoted to a full-width gradient CTA with a nebula glow. */}
      <div className="relative px-3 pb-3">
        <button
          onClick={handleNewChat}
          disabled={creatingChat}
          className="group relative flex w-full items-center justify-center gap-2 overflow-hidden rounded-md bg-gradient-brand px-3 py-2.5 text-sm font-medium text-white shadow-glow-accent transition-all duration-base ease-motion-spring hover:-translate-y-0.5 hover:shadow-glow-nebula disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
          title="New chat in your workspace"
        >
          {/* Sheen sweep on hover. */}
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-slow ease-motion-out group-hover:translate-x-full"
          />
          <Plus className="h-4 w-4" />
          <span className="tracking-tight">New chat</span>
        </button>
      </div>

      <div className="relative flex-1 space-y-1 overflow-y-auto pb-3">
        {isLoading && projects.length === 0 && (
          <p className="px-4 py-3 font-mono text-xs text-text-muted">Loading…</p>
        )}
        {!isLoading && projects.length === 0 && (
          <div className="px-4 py-8 text-center">
            <div className="relative mx-auto mb-4 grid h-14 w-14 place-items-center">
              <span
                aria-hidden
                className="absolute inset-0 rounded-md bg-gradient-brand opacity-20 blur-xl"
              />
              <span className="relative grid h-12 w-12 place-items-center rounded-xl border border-hairline-soft/40 bg-surface-soft/60">
                <MessageSquare className="h-5 w-5 text-text-secondary" />
              </span>
            </div>
            <p className="mb-4 text-xs leading-relaxed text-text-secondary">
              Start a conversation or spin up a new project to organize your
              work.
            </p>
            <div className="flex flex-col gap-2">
              <button
                onClick={handleNewChat}
                disabled={creatingChat}
                className="rounded-md bg-gradient-brand px-3 py-2 text-xs font-medium text-white shadow-glow-accent transition-transform duration-base ease-motion-spring hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
              >
                New chat
              </button>
              <button
                onClick={() => setCreateProjectOpen(true)}
                className="font-mono text-xs text-text-muted transition-colors hover:text-ink"
              >
                + New project
              </button>
            </div>
          </div>
        )}

        {modulesWithDashboards.length > 0 && (
          <div className="pt-2">
            <SectionEyebrow label="Modules" />
            <div className="space-y-0.5 px-2">
              {modulesWithDashboards.map((m) => {
                const isActive = activeModuleDashboard === m.name;
                return (
                  <button
                    key={m.name}
                    onClick={() => {
                      isActive
                        ? closeModuleDashboard()
                        : openModuleDashboard(m.name);
                      closeMobileSidebar();
                    }}
                    title={m.tooltip}
                    className={`group relative flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left transition-all duration-fast ${
                      isActive
                        ? "bg-gradient-to-r from-accent-cobalt/15 via-accent-violet/10 to-transparent text-ink"
                        : "text-text-secondary hover:bg-surface-soft/60 hover:text-ink"
                    }`}
                  >
                    {isActive && (
                      <span
                        aria-hidden
                        className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-md bg-gradient-brand"
                      />
                    )}
                    {m.icon_url ? (
                      <img
                        src={m.icon_url}
                        className="h-4 w-4 flex-shrink-0"
                        alt=""
                      />
                    ) : (
                      <Package
                        className={`h-4 w-4 flex-shrink-0 ${isActive ? "text-accent-cobalt" : "text-text-muted"}`}
                      />
                    )}
                    <span className="flex-1 truncate text-xs font-medium">
                      {m.display_name}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* CHATS — flat list of the active project's conversations */}
        {activeProjectId && (
          <div className="pt-3">
            <SectionEyebrow
              label="Chats"
              meta={activeProjectLabel ? `· ${activeProjectLabel}` : undefined}
              action={
                <button
                  onClick={() =>
                    activeProject && setCreateConvFor(activeProject)
                  }
                  className="rounded p-0.5 text-text-muted transition-colors hover:bg-surface-soft hover:text-accent-cobalt focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cobalt"
                  title="New conversation"
                  aria-label="New conversation"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              }
            />

            <div className="space-y-0.5 px-2">
              {activeConversations.length === 0 && (
                <button
                  onClick={() =>
                    activeProject && setCreateConvFor(activeProject)
                  }
                  className="flex w-full items-center gap-2 rounded-md border border-dashed border-hairline-soft/40 px-2.5 py-2.5 font-mono text-xs text-text-muted transition-colors hover:border-accent-cobalt/40 hover:text-accent-cobalt focus:outline-none"
                >
                  <Plus className="h-3.5 w-3.5" />
                  New conversation
                </button>
              )}

              {activeConversations.map((conv) => {
                const isActive = currentSessionId === conv.id;
                return (
                  <div
                    key={conv.id}
                    onClick={() => {
                      closeModuleDashboard();
                      loadSession(conv.id);
                      closeMobileSidebar();
                    }}
                    className={`group relative flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 transition-colors duration-fast ${
                      isActive
                        ? "bg-accent-cobalt/[0.08] text-ink ring-1 ring-inset ring-accent-cobalt/20"
                        : "text-text-secondary hover:bg-surface-soft/60 hover:text-ink"
                    }`}
                  >
                    {isActive && (
                      <span
                        aria-hidden
                        className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-[50%] bg-accent-cobalt"
                      />
                    )}
                    <span className="grid h-4 w-4 flex-shrink-0 place-items-center">
                      <MessageSquare
                        className={`h-3.5 w-3.5 ${isActive ? "text-accent-cobalt" : "text-text-muted"}`}
                      />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div
                        className={`truncate text-xs ${isActive ? "font-medium text-ink" : "text-text-secondary group-hover:text-ink"}`}
                      >
                        {conv.name}
                      </div>
                      <div className="truncate font-mono text-[10px] text-text-muted">
                        {formatRelativeTime(conv.updated_at)}
                      </div>
                    </div>
                    {conv.message_count > 0 && (
                      <span
                        className={`flex-shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10px] transition-opacity group-hover:opacity-0 ${
                          isActive
                            ? "bg-accent-cobalt/15 text-accent-cobalt"
                            : "bg-surface-soft text-text-muted"
                        }`}
                      >
                        {conv.message_count}
                      </span>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete({
                          type: "conv",
                          id: conv.id,
                          projectId: conv.project_id,
                        });
                      }}
                      className="absolute right-2 rounded p-1 text-text-muted opacity-100 transition-colors hover:bg-surface-soft hover:text-semantic-danger focus:outline-none focus-visible:ring-1 focus-visible:ring-semantic-danger md:opacity-0 md:group-hover:opacity-100"
                      aria-label={`Delete conversation ${conv.name}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </>
  );

  return (
    <>
      {isMobile ? (
        <>
          {mobileSidebarOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
              onClick={closeMobileSidebar}
              aria-hidden
            />
          )}
          <aside
            data-surface="dark"
            className={`fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col overflow-hidden border-r border-hairline-soft/25 bg-bg-100 transition-transform duration-200 ease-out md:hidden ${
              mobileSidebarOpen ? "translate-x-0" : "-translate-x-full"
            }`}
          >
            {sidebarBody}
          </aside>
        </>
      ) : (
        <motion.aside
          initial={reduce ? false : { opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          data-surface="dark"
          style={{ width: sidebarWidth }}
          className="relative flex flex-shrink-0 flex-col overflow-hidden border-r border-hairline-soft/25 bg-bg-100"
        >
          {/* Drag the right edge to resize the sidebar (kept within bounds — aside is overflow-hidden) */}
          <ResizeHandle
            side="right"
            width={sidebarWidth}
            min={200}
            max={480}
            onResize={setSidebarWidth}
            className="absolute bottom-0 right-0 top-0 z-30 w-2 cursor-col-resize transition-colors hover:bg-accent-cobalt/30"
          />
          {sidebarBody}
        </motion.aside>
      )}

      <CreateProjectModal
        isOpen={createProjectOpen}
        onClose={() => setCreateProjectOpen(false)}
      />
      <CreateConversationModal
        isOpen={!!createConvFor}
        projectId={createConvFor?.id ?? ""}
        projectName={createConvFor?.name ?? ""}
        onClose={() => setCreateConvFor(null)}
      />
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <motion.div
            initial={reduce ? false : { opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            data-surface="dark"
            className="w-80 rounded-xl border border-hairline-soft/40 bg-bg-000 p-6 shadow-modal"
          >
            <p className="mb-4 text-sm text-ink">
              Delete this{" "}
              {confirmDelete.type === "project"
                ? "project and all its conversations"
                : "conversation"}
              ? This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="rounded-md px-3 py-1.5 text-sm text-text-secondary transition-colors hover:text-ink"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirmed}
                className="rounded-md bg-semantic-danger px-3 py-1.5 text-sm text-white transition-colors hover:bg-semantic-danger/90"
              >
                Delete
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </>
  );
}
