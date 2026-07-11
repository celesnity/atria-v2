import { HelpCircle } from 'lucide-react';
import type { BlockBridge } from './MaintenanceAnswer';

interface Props {
  /** The model's clarification ask (shown in the full variant only). */
  ask?: string;
  missingFields: string[];
  /** Full variant replaces the answer body; compact sits below a valid answer. */
  variant: 'full' | 'compact';
  bridge: BlockBridge;
}

/**
 * Inline clarification / data-collection prompt: lists the fields the copilot
 * needs and prefills the chat input on click — the reply is just the next
 * chat message, no separate request/response protocol.
 */
export function ClarificationCard({ ask, missingFields, variant, bridge }: Props) {
  return (
    <div className={`mx-4 mb-3 rounded-md bg-accent-secondary-100/5 border border-accent-secondary-100/20 px-3 py-2.5 ${variant === 'full' ? 'mt-3' : ''}`}>
      <div className="flex items-center gap-2 mb-1.5">
        <HelpCircle className="w-3.5 h-3.5 text-accent-secondary-100 flex-shrink-0" />
        <span className="text-xs font-medium text-text-100">More information needed</span>
      </div>
      {variant === 'full' && ask && (
        <p className="text-sm text-text-100 whitespace-pre-wrap leading-relaxed mb-2">{ask}</p>
      )}
      {missingFields.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {missingFields.map((field, i) => (
            <button
              key={i}
              onClick={() => bridge.prefillDraft(`${field}: `)}
              className="px-2 py-1 rounded-md bg-bg-200 border border-border-300/20 text-[11px] font-mono text-text-200 hover:bg-bg-300 transition-colors"
              title="Prefill the chat input with this field"
            >
              {field}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
