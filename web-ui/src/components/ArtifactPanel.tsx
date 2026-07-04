import { useMemo, useState } from 'react';
import { LayoutGrid, Rows3, FileText, Trash2, Loader2, Search } from 'lucide-react';
import type { Artifact } from '../types';
import { ArtifactThumbnail } from './ArtifactThumbnail';

type ScopeFilter = 'all' | 'conversation' | 'project';
type ViewMode = 'grid' | 'list';

interface ArtifactPanelProps {
  artifacts: Artifact[];
  isLoading?: boolean;
  onDelete?: (artifactId: number) => void;
  onPreview?: (artifact: Artifact) => void;
  className?: string;
}

const SCOPES: { key: ScopeFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'conversation', label: 'Conversation' },
  { key: 'project', label: 'Project' },
];

export function ArtifactPanel({
  artifacts,
  isLoading = false,
  onDelete,
  onPreview,
  className = '',
}: ArtifactPanelProps) {
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');

  // Filter and search artifacts
  const filteredArtifacts = useMemo(() => {
    return artifacts.filter((artifact) => {
      // Apply scope filter
      if (scopeFilter === 'conversation' && !artifact.conversation_id) return false;
      if (scopeFilter === 'project' && artifact.conversation_id) return false;

      // Apply search filter
      const title = artifact.title?.toLowerCase() || '';
      const query = searchQuery.toLowerCase();
      return title.includes(query);
    });
  }, [artifacts, scopeFilter, searchQuery]);

  const hasBothScopes = artifacts.some((a) => a.conversation_id) &&
    artifacts.some((a) => !a.conversation_id);

  return (
    <div className={`artifact-panel flex flex-col h-full bg-canvas ${className}`}>
      {/* Header */}
      <div className="flex-shrink-0 border-b border-hairline-soft/60 px-3 pt-3 pb-2.5">
        <div className="flex items-baseline gap-2 mb-3">
          <h2 className="text-[13px] font-mono uppercase tracking-wide text-ink/70">Artifacts</h2>
          <span className="text-[11px] font-mono text-ink/35">{artifacts.length}</span>
        </div>

        {/* Search Bar */}
        <div className="relative mb-2.5">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink/35"
            strokeWidth={2}
          />
          <input
            type="text"
            placeholder="Search artifacts…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-[13px] rounded-md bg-surface-soft/40 border border-hairline-soft/60 text-ink placeholder:text-ink/35 transition-colors duration-fast focus:outline-none focus:border-accent-cobalt/60 focus:bg-canvas focus-visible:ring-1 focus-visible:ring-accent-cobalt/40"
          />
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between gap-2">
          {/* Scope Filter — segmented control on the brand surface */}
          {hasBothScopes ? (
            <div className="inline-flex items-center gap-0.5 rounded-md border border-hairline-soft/40 bg-surface-soft/40 p-0.5">
              {SCOPES.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setScopeFilter(key)}
                  className={[
                    'px-2.5 py-1 text-[11px] font-mono rounded-[4px] transition-all duration-fast cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cobalt',
                    scopeFilter === key
                      ? 'bg-canvas text-ink shadow-soft'
                      : 'text-text-muted hover:text-ink',
                  ].join(' ')}
                >
                  {label}
                </button>
              ))}
            </div>
          ) : (
            <span />
          )}

          {/* View Mode Toggle */}
          <div className="inline-flex items-center gap-0.5 rounded-md border border-hairline-soft/40 bg-surface-soft/40 p-0.5">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-1 rounded-[4px] transition-colors duration-fast cursor-pointer ${
                viewMode === 'grid'
                  ? 'bg-canvas text-accent-cobalt shadow-soft'
                  : 'text-ink/40 hover:text-ink'
              }`}
              title="Grid view"
              aria-label="Grid view"
              aria-pressed={viewMode === 'grid'}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`p-1 rounded-[4px] transition-colors duration-fast cursor-pointer ${
                viewMode === 'list'
                  ? 'bg-canvas text-accent-cobalt shadow-soft'
                  : 'text-ink/40 hover:text-ink'
              }`}
              title="List view"
              aria-label="List view"
              aria-pressed={viewMode === 'list'}
            >
              <Rows3 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-text-muted flex flex-col items-center">
              <Loader2 className="w-5 h-5 animate-spin text-accent-cobalt" strokeWidth={2} aria-hidden="true" />
              <p className="mt-2 text-[12px] font-mono text-text-muted">Loading artifacts…</p>
            </div>
          </div>
        )}

        {!isLoading && filteredArtifacts.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 px-4 select-none">
            <div className="relative grid h-14 w-14 place-items-center">
              <span
                aria-hidden
                className="absolute inset-0 rounded-md bg-gradient-brand opacity-20 blur-lg"
              />
              <span className="relative grid h-11 w-11 place-items-center rounded-xl border border-hairline-soft/40 bg-surface-soft/60 text-text-secondary">
                <FileText className="w-4 h-4" />
              </span>
            </div>
            <p className="text-[12px] font-mono text-text-muted text-center">
              {artifacts.length === 0
                ? 'No artifacts yet'
                : 'No artifacts match your search'}
            </p>
          </div>
        )}

        {!isLoading && filteredArtifacts.length > 0 && viewMode === 'grid' && (
          <div className="p-3 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-2 lg:grid-cols-3">
            {filteredArtifacts.map((artifact) => (
              <ArtifactThumbnail
                key={artifact.id}
                artifact={artifact}
                onDelete={onDelete}
                onPreview={onPreview}
              />
            ))}
          </div>
        )}

        {!isLoading && filteredArtifacts.length > 0 && viewMode === 'list' && (
          <div className="divide-y divide-hairline-soft/50">
            {filteredArtifacts.map((artifact) => (
              <div
                key={artifact.id}
                className="group px-3 py-2.5 hover:bg-surface-soft/40 cursor-pointer transition-colors duration-fast"
                onClick={() => onPreview?.(artifact)}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-[13px] font-medium text-ink truncate">
                      {artifact.title || 'Untitled'}
                    </h3>
                    <div className="flex items-center gap-1.5 mt-1">
                      <ScopeBadge isConversation={!!artifact.conversation_id} />
                      <span className="inline-flex items-center text-[10px] font-mono px-1.5 py-0.5 rounded-[3px] bg-surface-soft/60 text-text-secondary">
                        {artifact.type}
                      </span>
                      <span className="text-[10px] font-mono text-ink/35 ml-auto">
                        {new Date(artifact.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete?.(artifact.id);
                    }}
                    aria-label={`Delete ${artifact.title || 'artifact'}`}
                    className="flex-shrink-0 p-1.5 rounded-md text-ink/35 opacity-0 group-hover:opacity-100 hover:text-semantic-danger hover:bg-semantic-danger/10 transition-all duration-fast cursor-pointer"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer Stats */}
      {!isLoading && (
        <div className="flex-shrink-0 border-t border-hairline-soft/60 px-3 py-2 bg-surface-soft/30 text-[11px] font-mono text-text-muted">
          {filteredArtifacts.length} of {artifacts.length}
        </div>
      )}
    </div>
  );
}

/** Scope pill using the brand accent spine: cobalt = conversation, violet = project. */
function ScopeBadge({ isConversation }: { isConversation: boolean }) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded-[3px]',
        isConversation
          ? 'bg-accent-cobalt/12 text-accent-cobalt'
          : 'bg-accent-violet/12 text-accent-violet',
      ].join(' ')}
    >
      {isConversation ? 'Conversation' : 'Project'}
    </span>
  );
}
