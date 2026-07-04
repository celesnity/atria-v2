import { useEffect, useRef, useState } from 'react';
import {
  FileText,
  Code2,
  Image as ImageIcon,
  BarChart3,
  Paperclip,
  Globe,
  Pin,
  MoreHorizontal,
  RefreshCw,
  Box,
  type LucideIcon,
} from 'lucide-react';
import { useArtifactsStore } from '../../stores/artifacts';
import { useChatStore } from '../../stores/chat';
import { useViewerTabsStore } from '../../stores/viewerTabs';
import { NodeContextMenu, type MenuItem } from '../ArtifactViewer/tree/NodeContextMenu';
import { DeleteConfirmDialog } from '../ArtifactViewer/tree/DeleteConfirmDialog';
import type { Artifact } from '../../types';

// ── Type icon + color ─────────────────────────────────────────────────────────

const TYPE_META: Record<string, { Icon: LucideIcon; color: string; label: string }> = {
  report: { Icon: FileText,  color: 'text-blue-400',   label: 'Report' },
  code:   { Icon: Code2,     color: 'text-accent-magenta', label: 'Code'   },
  image:  { Icon: ImageIcon, color: 'text-pink-400',   label: 'Image'  },
  data:   { Icon: BarChart3, color: 'text-green-400',  label: 'Data'   },
  web:    { Icon: Globe,     color: 'text-orange-400', label: 'Web'    },
  file:   { Icon: Paperclip, color: 'text-text-muted', label: 'File'   },
};

function getFilename(ref: string | null): string {
  if (!ref) return 'Untitled';
  return ref.split('/').pop() ?? ref;
}

function ArtifactRow({
  artifact,
  conversationId,
}: {
  artifact: Artifact;
  conversationId: string;
}) {
  const { togglePin, renameArtifact, deleteArtifact } = useArtifactsStore();
  const openTab = useViewerTabsStore(s => s.openTab);
  const meta = TYPE_META[artifact.type] ?? TYPE_META.file;
  const TypeIcon = meta.Icon;
  const name = artifact.title || getFilename(artifact.payload_ref);

  const openable = !!artifact.payload_ref;

  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draftName, setDraftName] = useState(name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) {
      setDraftName(name);
      // Focus + select the basename after the input mounts.
      requestAnimationFrame(() => inputRef.current?.select());
    }
  }, [renaming]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleOpen = () => {
    if (!artifact.payload_ref) return;
    openTab(conversationId, artifact.payload_ref);
  };

  const commitRename = async () => {
    const next = draftName.trim();
    setRenaming(false);
    if (!next || next === name) return;
    try {
      await renameArtifact(conversationId, artifact.id, next);
    } catch {
      /* keep the row as-is on failure */
    }
  };

  const onKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!openable || renaming) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleOpen();
    }
  };

  const openMenu = (e: React.MouseEvent) => {
    e.stopPropagation();
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setMenu({ x: rect.right, y: rect.bottom });
  };

  const menuItems: Array<MenuItem | 'divider'> = [
    {
      label: artifact.pinned ? 'Unpin' : 'Pin',
      onSelect: () => togglePin(conversationId, artifact.id, artifact.pinned),
    },
    { label: 'Rename', onSelect: () => setRenaming(true), disabled: !openable },
    'divider',
    { label: 'Delete', danger: true, onSelect: () => setConfirmOpen(true) },
  ];

  return (
    <div
      role={openable && !renaming ? 'button' : undefined}
      tabIndex={openable && !renaming ? 0 : -1}
      onClick={openable && !renaming ? handleOpen : undefined}
      onKeyDown={onKey}
      aria-label={openable ? `Open ${name}` : undefined}
      className={`group flex items-center gap-2 rounded-lg px-2 py-1.5 transition-all duration-fast hover:bg-surface-soft/60 focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cobalt ${
        openable && !renaming ? 'cursor-pointer hover:translate-x-0.5' : ''
      }`}
    >
      {/* Type glyph in a tinted chip — consistent alignment + a premium app feel. */}
      <span className="grid h-6 w-6 flex-shrink-0 place-items-center rounded-md border border-hairline-soft/40 bg-surface-soft/50">
        <TypeIcon className={`h-3.5 w-3.5 ${meta.color}`} aria-label={meta.label} />
      </span>

      <div className="min-w-0 flex-1">
        {renaming ? (
          <input
            ref={inputRef}
            value={draftName}
            onChange={e => setDraftName(e.target.value)}
            onClick={e => e.stopPropagation()}
            onBlur={commitRename}
            onKeyDown={e => {
              e.stopPropagation();
              if (e.key === 'Enter') {
                e.preventDefault();
                void commitRename();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                setRenaming(false);
              }
            }}
            className="w-full rounded border border-hairline-soft bg-canvas px-1.5 py-0.5 font-mono text-[11px] text-ink outline-none focus:border-accent-cobalt focus:ring-1 focus:ring-accent-cobalt/40"
          />
        ) : (
          <>
            <p
              className="truncate font-mono text-[11px] leading-tight text-text-secondary transition-colors group-hover:text-ink"
              title={artifact.payload_ref ?? ''}
            >
              {name}
            </p>
            {artifact.payload_ref && (
              <p className="mt-0.5 truncate font-mono text-[10px] leading-none text-text-muted">
                {artifact.payload_ref.replace(/^.*\/([^/]+\/[^/]+)$/, '$1')}
              </p>
            )}
          </>
        )}
      </div>

      {artifact.pinned && !renaming && (
        <Pin
          className="h-2.5 w-2.5 flex-shrink-0 fill-current text-amber-400 opacity-70 group-hover:opacity-0"
          aria-label="Pinned"
        />
      )}

      {!renaming && (
        <button
          onClick={openMenu}
          className="rounded p-0.5 text-text-muted opacity-0 transition-colors hover:bg-surface-soft hover:text-ink focus:outline-none focus-visible:opacity-100 focus-visible:ring-1 focus-visible:ring-accent-cobalt group-hover:opacity-100"
          title="Actions"
          aria-label="Artifact actions"
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
      )}

      {menu && (
        <NodeContextMenu x={menu.x} y={menu.y} items={menuItems} onClose={() => setMenu(null)} />
      )}

      <DeleteConfirmDialog
        open={confirmOpen}
        title="Delete file"
        message={`Delete "${name}"? This removes the file from disk and cannot be undone.`}
        onConfirm={() => deleteArtifact(conversationId, artifact.id)}
        onClose={() => setConfirmOpen(false)}
      />
    </div>
  );
}

export function ArtifactsPanel() {
  const currentSessionId = useChatStore(s => s.currentSessionId);
  const { artifacts, loading, scanning, scanArtifacts } = useArtifactsStore();

  // Auto-scan the conversation folder whenever the active session changes.
  // scanArtifacts walks the working directory and upserts new files into DB.
  useEffect(() => {
    if (!currentSessionId || isNaN(parseInt(currentSessionId, 10))) return;
    scanArtifacts(currentSessionId).catch(() => {});
  }, [currentSessionId]);

  if (!currentSessionId) {
    return null;
  }

  const convInt = parseInt(currentSessionId, 10);
  if (isNaN(convInt)) return null;

  const items = artifacts[currentSessionId] ?? [];
  const isLoading = loading[currentSessionId] ?? false;

  return (
    <div className="flex min-h-0 flex-col border-t border-hairline-soft/25">
      {/* Section header — eyebrow + count on the left, scan control on the right. */}
      <div className="flex items-center gap-2 px-3 pb-2 pt-3">
        <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-text-muted">
          Artifacts
        </span>
        {items.length > 0 && (
          <span className="rounded-[50%] bg-surface-soft px-1.5 py-0.5 font-mono text-[10px] text-text-muted">
            {items.length}
          </span>
        )}
        <span className="h-px flex-1 bg-hairline-soft/40" aria-hidden />
        <button
          onClick={() => scanArtifacts(currentSessionId)}
          disabled={scanning}
          title="Scan working directory"
          className="rounded p-1 text-text-muted transition-colors hover:bg-surface-soft hover:text-ink disabled:opacity-40 focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cobalt"
        >
          <RefreshCw className={`h-3 w-3 ${scanning ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Content */}
      <div className="max-h-48 space-y-0.5 overflow-y-auto px-2 pb-1.5">
        {isLoading && items.length === 0 && (
          <p className="px-1 py-1 font-mono text-[11px] text-text-muted">Loading…</p>
        )}
        {!isLoading && items.length === 0 && (
          <div className="px-3 py-4 text-center">
            <div className="relative mx-auto mb-3 grid h-11 w-11 place-items-center">
              <span
                aria-hidden
                className="absolute inset-0 rounded-[50%] bg-gradient-brand opacity-20 blur-lg"
              />
              <span className="relative grid h-10 w-10 place-items-center rounded-xl border border-hairline-soft/40 bg-surface-soft/60">
                <Box className="h-4 w-4 text-text-secondary" />
              </span>
            </div>
            <p className="mb-2.5 font-mono text-[11px] text-text-muted">No artifacts yet</p>
            <button
              onClick={() => scanArtifacts(currentSessionId)}
              className="inline-flex items-center gap-1.5 rounded-md border border-hairline-soft/40 px-2.5 py-1.5 font-mono text-[11px] text-text-secondary transition-colors hover:border-accent-cobalt/40 hover:text-accent-cobalt focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cobalt"
            >
              Scan workspace
              <RefreshCw className="h-3 w-3" />
            </button>
          </div>
        )}
        {items.map(artifact => (
          <ArtifactRow
            key={artifact.id}
            artifact={artifact}
            conversationId={currentSessionId}
          />
        ))}
      </div>
    </div>
  );
}
