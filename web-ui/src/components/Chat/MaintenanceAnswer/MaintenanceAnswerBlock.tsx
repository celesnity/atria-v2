import { useState } from 'react';
import { AlertTriangle, CheckCircle2, ShieldAlert, ShieldCheck } from 'lucide-react';
import type { MaintenanceAnswerType, Message } from '../../../types';
import { useToastStore } from '../../../stores/toast';
import { CitationChips } from './CitationChips';
import { ClarificationCard } from './ClarificationCard';
import { ExactQuoteCard } from './ExactQuoteCard';
import { SuggestionChips } from './SuggestionChips';

interface Props {
  message: Message;
}

const BAND_STYLES: Record<string, { dot: string; text: string; label: string }> = {
  high:   { dot: 'bg-green-500',  text: 'text-green-600',  label: 'High confidence' },
  medium: { dot: 'bg-yellow-500', text: 'text-yellow-600', label: 'Medium confidence' },
  low:    { dot: 'bg-red-500',    text: 'text-red-500',    label: 'Low confidence' },
};

const ANSWER_TYPE_LABELS: Record<MaintenanceAnswerType, string> = {
  extractive: 'Verbatim extract',
  synthesized: 'Synthesized',
  clarification_needed: 'Needs clarification',
};

/**
 * Renders a maintenance_copilot structured answer: the synthesized summary and
 * the verbatim quote as distinct blocks, answer-type + sensitivity + confidence
 * chips, a mandatory-review banner, clickable citations into the source viewer,
 * follow-up suggestion chips, inline clarification prompts, and the
 * licensed-engineer sign-off.
 */
export function MaintenanceAnswerBlock({ message }: Props) {
  const {
    ma_answer = '',
    ma_answer_type = 'synthesized',
    ma_exact_quote,
    ma_is_sensitive = false,
    ma_citations = [],
    ma_related_suggestions = [],
    ma_needs_user_input = false,
    ma_missing_fields = [],
    ma_confidence,
    ma_confidence_band = 'low',
    ma_review_required = false,
    ma_advisory_note = '',
    ma_validation_warnings = [],
    search_query,
  } = message;

  const band = BAND_STYLES[ma_confidence_band] ?? BAND_STYLES.low;
  const isClarification = ma_answer_type === 'clarification_needed';
  const [signing, setSigning] = useState(false);
  const [signedOff, setSignedOff] = useState(false);

  const handleSignoff = async () => {
    if (signing || signedOff) return;
    setSigning(true);
    try {
      // Generic connector passthrough — core no longer has a module-specific
      // maintenance route; every module reaches its connector the same way.
      const resp = await fetch('/api/modules/maintenance_copilot/connector/signoff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: search_query,
          answer_summary: ma_answer.slice(0, 500),
          decision: 'acknowledged',
          citations: ma_citations,
          answer_type: ma_answer_type,
          is_sensitive: ma_is_sensitive,
          exact_quote: ma_exact_quote ? ma_exact_quote.slice(0, 500) : null,
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
      {/* Header: label + answer-type + sensitivity + confidence chips */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border-300/10">
        <ShieldCheck className="w-4 h-4 text-accent-secondary-100 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-xs font-mono text-text-300 mr-2">maintenance copilot</span>
          {search_query && (
            <span className="text-sm text-text-100 font-medium truncate">{search_query}</span>
          )}
        </div>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-bg-200 text-text-300 flex-shrink-0">
          {ANSWER_TYPE_LABELS[ma_answer_type] ?? ma_answer_type}
        </span>
        {ma_is_sensitive && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-600 flex-shrink-0"
                title="Contains PII, financial, medical, or legal content">
            <ShieldAlert className="w-3 h-3" /> Sensitive
          </span>
        )}
        {!isClarification && (
          <div className="flex items-center gap-1.5 flex-shrink-0" title={
            ma_confidence !== undefined ? `retrieval score ${ma_confidence}` : undefined
          }>
            <span className={`w-2 h-2 rounded-full ${band.dot}`} />
            <span className={`text-xs font-medium ${band.text}`}>{band.label}</span>
          </div>
        )}
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

      {/* Body */}
      {isClarification ? (
        <ClarificationCard ask={ma_answer} missingFields={ma_missing_fields} variant="full" />
      ) : (
        <>
          <div className="px-4 py-3">
            <p className="text-sm text-text-100 whitespace-pre-wrap leading-relaxed">{ma_answer}</p>
          </div>
          {!!ma_exact_quote && <ExactQuoteCard quote={ma_exact_quote} />}
          {ma_needs_user_input && (
            <ClarificationCard missingFields={ma_missing_fields} variant="compact" />
          )}
          <CitationChips citations={ma_citations} exactQuote={ma_exact_quote} />
          <SuggestionChips suggestions={ma_related_suggestions} />
        </>
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
