import { Settings2, Lock, Brain } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chat';

const MODE_STYLES = {
  normal: 'bg-bg-400/40 text-text-200 border-hairline-soft hover:bg-bg-400/60',
  plan: 'bg-accent-secondary-900 text-accent-secondary-100 border-accent-secondary-900/50 hover:bg-accent-secondary-900/80',
} as const;

const AUTONOMY_STYLES = {
  'Manual': 'bg-bg-400/40 text-text-200 border-hairline-soft hover:bg-bg-400/60',
  'Semi-Auto': 'bg-accent-secondary-900 text-accent-secondary-100 border-accent-secondary-900/50 hover:bg-accent-secondary-900/80',
  'Auto': 'bg-success-100/10 text-success-100 border-success-100/20 hover:bg-success-100/15',
} as const;

const THINKING_STYLES: Record<string, string> = {
  'Off':           'bg-bg-200 text-text-500 border-hairline-soft hover:bg-bg-300',
  'Low':           'bg-cyan-500/10 text-cyan-600 border-cyan-500/20 hover:bg-cyan-500/15',
  'Medium':        'bg-success-100/10 text-success-100 border-success-100/20 hover:bg-success-100/15',
  'High':          'bg-yellow-500/10 text-yellow-600 border-yellow-500/20 hover:bg-yellow-500/15',
} as const;

export function StatusBar() {
  const { t } = useTranslation('chat');
  const status = useChatStore(state => state.status);
  const thinkingLevel = useChatStore(state => state.thinkingLevel);
  const toggleMode = useChatStore(state => state.toggleMode);
  const cycleAutonomy = useChatStore(state => state.cycleAutonomy);
  const cycleThinkingLevel = useChatStore(state => state.cycleThinkingLevel);

  if (!status) return null;

  // Compact for the narrow rail: icon + value only (the category lives in the
  // tooltip), tight padding so the toolbar stays on one or two rows.
  const pillBase = 'inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[11px] font-medium cursor-pointer transition-colors select-none active:scale-[0.98] whitespace-nowrap';

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {/* Mode pill */}
      <button
        onClick={toggleMode}
        className={`${pillBase} ${MODE_STYLES[status.mode]}`}
        title={t('statusBar.modeTitle')}
      >
        <Settings2 className="w-3 h-3" strokeWidth={2} />
        {status.mode === 'normal' ? t('statusBar.modeNormal') : t('statusBar.modePlan')}
      </button>

      {/* Autonomy pill */}
      <button
        onClick={cycleAutonomy}
        className={`${pillBase} ${AUTONOMY_STYLES[status.autonomy_level]}`}
        title={t('statusBar.autonomyTitle')}
      >
        <Lock className="w-3 h-3" strokeWidth={2} />
        {status.autonomy_level}
      </button>

      {/* Thinking pill */}
      <button
        onClick={cycleThinkingLevel}
        className={`${pillBase} ${THINKING_STYLES[thinkingLevel] || THINKING_STYLES['Medium']}`}
        title={t('statusBar.thinkingTitle')}
      >
        <Brain className="w-3 h-3" strokeWidth={2} />
        {thinkingLevel}
      </button>
    </div>
  );
}
