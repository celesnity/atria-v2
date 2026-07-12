import { FileText } from 'lucide-react';
import type { MaintenanceCitation } from '../../../types';
import { useChatStore } from '../../../stores/chat';
import { useViewerTabsStore } from '../../../stores/viewerTabs';

interface Props {
  citations: MaintenanceCitation[];
  /** The verified verbatim quote — used as the reveal anchor for the citation
   *  that carries char offsets (immune to CRLF/front-matter offset drift). */
  exactQuote?: string | null;
}

const MODULE = 'maintenance_copilot';

/** Confidence % tint mirroring the card's band thresholds. */
function scoreClass(score: number): string {
  if (score >= 0.6) return 'text-semantic-success';
  if (score >= 0.4) return 'text-semantic-warning';
  return 'text-semantic-danger';
}

/** Resolve a stored source path (may be absolute on the server) to a module-relative one. */
function moduleRelative(sourcePath: string): string | null {
  const norm = sourcePath.replace(/\\/g, '/');
  const idx = norm.indexOf(`${MODULE}/`);
  if (idx >= 0) return norm.slice(idx + MODULE.length + 1);
  // Already relative (no module prefix, not absolute) — use as-is.
  if (!norm.startsWith('/') && !/^[A-Za-z]:/.test(norm)) return norm;
  return null;
}

/**
 * Clickable source chips: filename + revision + ATA + page (when real) +
 * retrieval-confidence %. Clicking opens the cited manual in the artifact
 * viewer and reveals the quoted passage.
 */
export function CitationChips({ citations, exactQuote }: Props) {
  const convId = useChatStore(s => s.currentSessionId);
  const openModuleFileTab = useViewerTabsStore(s => s.openModuleFileTab);

  if (citations.length === 0) return null;

  const handleOpen = (c: MaintenanceCitation) => {
    if (!convId || !c.source_path) return;
    const path = moduleRelative(c.source_path);
    if (!path) return;
    const hasAnchor = c.char_start != null;
    openModuleFileTab(convId, MODULE, path, {
      start: c.char_start ?? undefined,
      end: c.char_end ?? undefined,
      text: hasAnchor && exactQuote ? exactQuote : undefined,
      nonce: Date.now(),
    });
  };

  return (
    <div className="px-4 pb-3">
      <div className="text-[11px] font-mono text-text-400 mb-1.5">Sources</div>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => {
          const clickable = !!convId && !!c.source_path && !!moduleRelative(c.source_path);
          return (
            <button
              key={i}
              onClick={() => handleOpen(c)}
              disabled={!clickable}
              className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-bg-200 border border-border-300/20 text-[11px] text-text-200 transition-colors ${
                clickable ? 'hover:bg-bg-300 hover:border-border-300/40 cursor-pointer' : 'cursor-default'
              }`}
              title={c.citation}
            >
              <FileText className="w-3 h-3 text-accent-secondary-100 flex-shrink-0" />
              <span className="font-medium">{c.source_name || c.doc || 'DOC'}</span>
              {c.revision && <span className="text-text-400">{c.revision}</span>}
              {c.ata && <span className="text-text-400">ATA {c.ata}</span>}
              {c.page_number != null && <span className="text-text-400">p.{c.page_number}</span>}
              <span className={`font-mono ${scoreClass(c.confidence_score ?? 0)}`}>
                {Math.round((c.confidence_score ?? 0) * 100)}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
