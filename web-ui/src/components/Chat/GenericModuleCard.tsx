import { AlertTriangle, Boxes } from 'lucide-react';
import type { Message } from '../../types';

interface Props {
  message: Message;
}

const BAND_STYLES: Record<string, { dot: string; text: string; label: string }> = {
  high:   { dot: 'bg-green-500',  text: 'text-green-600',  label: 'High confidence' },
  medium: { dot: 'bg-yellow-500', text: 'text-yellow-600', label: 'Medium confidence' },
  low:    { dot: 'bg-red-500',    text: 'text-red-500',    label: 'Low confidence' },
};

/**
 * Fallback renderer for any service-module card that has no bespoke component
 * registered (card_type such as `"{module}_card"`). Surfaces the fields common
 * to every module's card: the answer text, an optional confidence band/dot, and
 * validation warnings — styled to match MaintenanceAnswerBlock.
 */
export function GenericModuleCard({ message }: Props) {
  const {
    card_module = 'module',
    card_answer = '',
    card_confidence_band,
    card_validation_warnings = [],
    search_query,
  } = message;

  const band = card_confidence_band ? BAND_STYLES[card_confidence_band] : undefined;
  const moduleLabel = card_module.replace(/_/g, ' ');

  return (
    <div className="bg-bg-000 border border-border-300/15 rounded-lg overflow-hidden animate-slide-up">
      {/* Header: module label + query + confidence chip */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border-300/10">
        <Boxes className="w-4 h-4 text-accent-secondary-100 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-xs font-mono text-text-300 mr-2">{moduleLabel}</span>
          {search_query && (
            <span className="text-sm text-text-100 font-medium truncate">{search_query}</span>
          )}
        </div>
        {band && (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span className={`w-2 h-2 rounded-full ${band.dot}`} />
            <span className={`text-xs font-medium ${band.text}`}>{band.label}</span>
          </div>
        )}
      </div>

      {/* Validation warnings */}
      {card_validation_warnings.length > 0 && (
        <div className="px-4 py-2.5 bg-yellow-500/10 border-b border-yellow-500/20 space-y-1">
          {card_validation_warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-yellow-600 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-yellow-700">{w}</p>
            </div>
          ))}
        </div>
      )}

      {/* Body */}
      <div className="px-4 py-3">
        <p className="text-sm text-text-100 whitespace-pre-wrap leading-relaxed">{card_answer}</p>
      </div>
    </div>
  );
}
