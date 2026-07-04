import { MessageCirclePlus } from 'lucide-react';
import { useChatStore } from '../../../stores/chat';

interface Props {
  suggestions: string[];
}

/** Related follow-up questions as one-click pills that send into the chat. */
export function SuggestionChips({ suggestions }: Props) {
  const isLoading = useChatStore(s => {
    const sid = s.currentSessionId;
    return sid ? !!s.sessionStates[sid]?.isLoading : false;
  });

  if (suggestions.length === 0) return null;

  return (
    <div className="px-4 pb-3">
      <div className="text-[11px] font-mono text-text-400 mb-1.5">Related</div>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.map((text, i) => (
          <button
            key={i}
            onClick={() => useChatStore.getState().sendMessage(text)}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-bg-200 border border-border-300/20 text-[11px] text-text-200 hover:bg-bg-300 hover:border-border-300/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Ask this follow-up"
          >
            <MessageCirclePlus className="w-3 h-3 text-accent-secondary-100 flex-shrink-0" />
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
