import { useState } from 'react';
import { ShieldCheck, AlertTriangle, CheckCircle2, FileText } from 'lucide-react';
import type { Message } from '../../types';
import { useToastStore } from '../../stores/toast';

interface Props {
  message: Message;
}

const BAND_STYLES: Record<string, { dot: string; text: string; label: string }> = {
  high:   { dot: 'bg-green-500',  text: 'text-green-600',  label: 'High confidence' },
  medium: { dot: 'bg-yellow-500', text: 'text-yellow-600', label: 'Medium confidence' },
  low:    { dot: 'bg-red-500',    text: 'text-red-500',    label: 'Low confidence' },
};

/**
 * Renders a maintenance_copilot answer as a native card: the grounded answer,
 * a color-coded confidence chip, a mandatory-manual-review banner when the
 * confidence floor is not met, clickable citation chips (doc + revision +
 * section), the advisory-only note, and a licensed-engineer sign-off button.
 */
export function MaintenanceAnswerBlock({ message }: Props) {
  const {
    ma_answer = '',
    ma_citations = [],
    ma_confidence,
    ma_confidence_band = 'low',
    ma_review_required = false,
    ma_advisory_note = '',
    ma_validation_warnings = [],
    search_query,
  } = message;

  const band = BAND_STYLES[ma_confidence_band] ?? BAND_STYLES.low;
  const [signing, setSigning] = useState(false);
  const [signedOff, setSignedOff] = useState(false);

  const handleSignoff = async () => {
    if (signing || signedOff) return;
    setSigning(true);
    try {
      const resp = await fetch('/api/maintenance/signoff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: search_query,
          answer_summary: ma_answer.slice(0, 500),
          decision: 'acknowledged',
          citations: ma_citations,
        }),
      });
      if (!resp.ok) throw new Error(`status ${resp.status}`);
      setSignedOff(true);
      useToastStore.getState().addToast('Sign-off recorded to the audit trail.', 'success');
    } catch {
      useToastStore.getState().addToast('Sign-off failed. Please try again.', 'error');
    } finally {
      setSigning(false);
    }
  };

  return (
    <div className="bg-bg-000 border border-border-300/15 rounded-lg overflow-hidden animate-slide-up">
      {/* Header: label + confidence chip */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border-300/10">
        <ShieldCheck className="w-4 h-4 text-accent-secondary-100 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-xs font-mono text-text-300 mr-2">maintenance copilot</span>
          {search_query && (
            <span className="text-sm text-text-100 font-medium truncate">{search_query}</span>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0" title={
          ma_confidence !== undefined ? `retrieval score ${ma_confidence}` : undefined
        }>
          <span className={`w-2 h-2 rounded-full ${band.dot}`} />
          <span className={`text-xs font-medium ${band.text}`}>{band.label}</span>
        </div>
      </div>

      {/* Mandatory manual review gate */}
      {ma_review_required && (
        <div className="flex items-start gap-2 px-4 py-2.5 bg-red-500/10 border-b border-red-500/20">
          <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-600 font-medium">
            Mandatory manual review — insufficient grounded evidence. Verify against the approved
            manuals before any dispatch decision.
          </p>
        </div>
      )}

      {/* Validation warnings */}
      {ma_validation_warnings.length > 0 && (
        <div className="px-4 py-2.5 bg-yellow-500/10 border-b border-yellow-500/20 space-y-1">
          {ma_validation_warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-yellow-700">{w}</p>
            </div>
          ))}
        </div>
      )}

      {/* Answer */}
      <div className="px-4 py-3">
        <p className="text-sm text-text-100 whitespace-pre-wrap leading-relaxed">{ma_answer}</p>
      </div>

      {/* Citation chips */}
      {ma_citations.length > 0 && (
        <div className="px-4 pb-3">
          <div className="text-[11px] font-mono text-text-400 mb-1.5">Sources</div>
          <div className="flex flex-wrap gap-1.5">
            {ma_citations.map((c, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-bg-200 border border-border-300/20 text-[11px] text-text-200"
                title={c.citation}
              >
                <FileText className="w-3 h-3 text-accent-secondary-100 flex-shrink-0" />
                <span className="font-medium">{c.doc || 'DOC'}</span>
                {c.revision && <span className="text-text-400">{c.revision}</span>}
                {c.ata && <span className="text-text-400">ATA {c.ata}</span>}
                <span className="text-text-400 font-mono">{c.chunk_id}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Footer: advisory note + sign-off */}
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-t border-border-300/10 bg-bg-100/30">
        <p className="text-[11px] text-text-400 italic min-w-0 flex-1">
          {ma_advisory_note || 'Advisory only — a licensed engineer must verify and sign off.'}
        </p>
        {signedOff ? (
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-green-600 flex-shrink-0">
            <CheckCircle2 className="w-4 h-4" /> Signed off
          </span>
        ) : (
          <button
            onClick={handleSignoff}
            disabled={signing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-ink text-canvas hover:bg-ink/80 disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0 transition-colors"
            title="Record a licensed-engineer sign-off to the audit trail"
          >
            {signing ? (
              <div className="w-3.5 h-3.5 border-[1.5px] border-canvas/60 border-t-transparent rounded-full animate-spin" />
            ) : (
              <ShieldCheck className="w-3.5 h-3.5" />
            )}
            Engineer sign-off
          </button>
        )}
      </div>
    </div>
  );
}
