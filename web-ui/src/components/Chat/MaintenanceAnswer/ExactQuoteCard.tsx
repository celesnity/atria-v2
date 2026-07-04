import { Copy, Quote } from 'lucide-react';
import { useToastStore } from '../../../stores/toast';

interface Props {
  quote: string;
}

/**
 * The verbatim document quote, visually distinct from the synthesized answer:
 * a monospace blockquote explicitly labeled as uncorrected source text (OCR
 * artifacts and typos are preserved by the backend's substring verification).
 */
export function ExactQuoteCard({ quote }: Props) {
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(quote);
      useToastStore.getState().addToast('Quote copied', 'success');
    } catch {
      useToastStore.getState().addToast('Copy failed', 'error');
    }
  };

  return (
    <div className="mx-4 mb-3 rounded-md bg-bg-100/50 border border-border-300/15 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border-300/10">
        <Quote className="w-3 h-3 text-accent-secondary-100 flex-shrink-0" />
        <span className="text-[10px] font-mono uppercase tracking-wide text-text-400 flex-1">
          verbatim from source — not corrected
        </span>
        <button
          onClick={handleCopy}
          className="p-1 rounded hover:bg-bg-200 text-text-400 hover:text-text-200 transition-colors"
          title="Copy quote"
        >
          <Copy className="w-3 h-3" />
        </button>
      </div>
      <blockquote className="px-3 py-2 border-l-2 border-accent-secondary-100 font-mono text-[13px] text-text-100 whitespace-pre-wrap leading-relaxed">
        {quote}
      </blockquote>
    </div>
  );
}
