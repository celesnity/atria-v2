import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Diamond } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface ThinkingBlockProps {
  content: string;
  level?: string;
  isActive?: boolean;
}

export function ThinkingBlock({ content, level, isActive }: ThinkingBlockProps) {
  const { t } = useTranslation('chat');
  const [isExpanded, setIsExpanded] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState(0);

  const isCritique = content.startsWith('[Critique]');

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setContentHeight(el.scrollHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="animate-slide-up pl-[26px]">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        aria-label={isExpanded ? t('thinkingBlock.collapse') : t('thinkingBlock.expand')}
        className={`flex items-center gap-1.5 py-0.5 text-left cursor-pointer rounded transition-colors ${isActive ? 'thinking-shimmer' : ''}`}
      >
        <Diamond
          className="w-3 h-3 text-ink/30 shrink-0"
          strokeWidth={2}
          fill={isCritique ? 'currentColor' : 'none'}
          aria-hidden="true"
        />
        <span className="text-[13px] text-ink/50 font-medium">
          {isCritique ? t('thinkingBlock.critique') : t('thinkingBlock.thought')}
        </span>
        {level && (
          <span className="text-[11px] text-ink/30 font-mono">· {level}</span>
        )}
        <ChevronDown
          className={`w-3 h-3 text-ink/30 transition-transform duration-fast ${isExpanded ? 'rotate-180' : ''}`}
        />
      </button>

      <div
        // While a block is actively streaming AND expanded, render at natural
        // height with NO transition: the 240ms max-height animation chasing a
        // ResizeObserver makes the item's height a perpetually-moving target,
        // which the chat auto-follow then fights → flicker. Completed blocks the
        // user toggles keep the smooth expand/collapse animation.
        className={
          isActive && isExpanded
            ? 'overflow-hidden'
            : 'overflow-hidden transition-all duration-base ease-motion-out'
        }
        style={{
          maxHeight: isActive && isExpanded
            ? 'none'
            : isExpanded ? `${contentHeight + 16}px` : '0px',
        }}
      >
        <div ref={contentRef} className="mt-2 ml-4 border-l border-hairline-soft pl-3 pb-2">
          <pre className="text-[12.5px] text-ink/50 whitespace-pre-wrap font-mono leading-[1.55] m-0 p-0 bg-transparent border-0">
            {content}
          </pre>
        </div>
      </div>
    </div>
  );
}
