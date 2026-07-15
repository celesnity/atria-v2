import { Settings2, Lock, Brain, Globe } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chat';
import { LanguageSwitcher } from '../ui/LanguageSwitcher';

type SegmentedOption<T extends string> = {
  value: T;
  label: string;
  description: string;
  colorClass: string;
};

function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: SegmentedOption<T>[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(opt => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 rounded-md border text-xs font-medium transition-all cursor-pointer select-none active:scale-[0.97] ${
            value === opt.value
              ? opt.colorClass
              : 'bg-surface-soft text-text-secondary border-hairline-soft hover:text-ink hover:bg-canvas'
          }`}
          title={opt.description}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

const MODE_OPTIONS: SegmentedOption<'normal' | 'plan'>[] = [
  {
    value: 'normal',
    label: 'Normal',
    description: 'Full tool access — agent can read files, run commands, and make changes',
    colorClass: 'bg-accent-cobalt/10 text-accent-cobalt border-accent-cobalt/25',
  },
  {
    value: 'plan',
    label: 'Plan',
    description: 'Read-only exploration — agent can only inspect, never modify',
    colorClass: 'bg-accent-secondary-900 text-accent-secondary-100 border-accent-secondary-900/50',
  },
];

const AUTONOMY_OPTIONS: SegmentedOption<'Manual' | 'Semi-Auto' | 'Auto'>[] = [
  {
    value: 'Manual',
    label: 'Manual',
    description: 'Approve each tool call individually',
    colorClass: 'bg-surface-soft text-ink border-hairline-soft ring-1 ring-inset ring-accent-cobalt/30',
  },
  {
    value: 'Semi-Auto',
    label: 'Semi-Auto',
    description: 'Auto-approve safe read-only tools; prompt for writes and commands',
    colorClass: 'bg-accent-secondary-900 text-accent-secondary-100 border-accent-secondary-900/50',
  },
  {
    value: 'Auto',
    label: 'Auto — Approve All',
    description: 'Automatically approve every tool call without prompting',
    colorClass: 'bg-success-100/10 text-success-100 border-success-100/20',
  },
];

const THINKING_OPTIONS: SegmentedOption<'Off' | 'Low' | 'Medium' | 'High'>[] = [
  {
    value: 'Off',
    label: 'Off',
    description: 'No chain-of-thought reasoning — fastest, cheapest',
    colorClass: 'bg-bg-200 text-text-500 border-hairline-soft ring-1 ring-inset ring-ink/20',
  },
  {
    value: 'Low',
    label: 'Low',
    description: 'Light reasoning pass — good for simple tasks',
    colorClass: 'bg-cyan-500/10 text-cyan-600 border-cyan-500/20',
  },
  {
    value: 'Medium',
    label: 'Medium',
    description: 'Balanced reasoning — default for most tasks',
    colorClass: 'bg-success-100/10 text-success-100 border-success-100/20',
  },
  {
    value: 'High',
    label: 'High',
    description: 'Deep reasoning — slower but best for complex problems',
    colorClass: 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20',
  },
];

export function GeneralSettings() {
  const { t } = useTranslation('settings');
  const status = useChatStore(state => state.status);
  const thinkingLevel = useChatStore(state => state.thinkingLevel);
  const toggleMode = useChatStore(state => state.toggleMode);
  const cycleAutonomy = useChatStore(state => state.cycleAutonomy);
  const cycleThinkingLevel = useChatStore(state => state.cycleThinkingLevel);

  const currentMode = status?.mode ?? 'normal';
  const currentAutonomy = status?.autonomy_level ?? 'Auto';
  const currentThinking = (status?.thinking_level ?? thinkingLevel) as 'Off' | 'Low' | 'Medium' | 'High';

  function setMode(v: 'normal' | 'plan') {
    if (v !== currentMode) toggleMode();
  }

  function setAutonomy(v: 'Manual' | 'Semi-Auto' | 'Auto') {
    const CYCLE = ['Manual', 'Semi-Auto', 'Auto'] as const;
    const steps = (CYCLE.indexOf(v) - CYCLE.indexOf(currentAutonomy as never) + 3) % 3;
    for (let i = 0; i < steps; i++) cycleAutonomy();
  }

  function setThinking(v: 'Off' | 'Low' | 'Medium' | 'High') {
    const CYCLE = ['Off', 'Low', 'Medium', 'High'] as const;
    const steps = (CYCLE.indexOf(v) - CYCLE.indexOf(currentThinking) + 4) % 4;
    for (let i = 0; i < steps; i++) cycleThinkingLevel();
  }

  const row = 'flex flex-col gap-3 py-5 border-b border-hairline-soft last:border-b-0';
  const label = 'flex items-center gap-2 text-sm font-[540] text-ink';
  const hint = 'text-xs text-text-muted leading-relaxed';

  return (
    <div className="max-w-2xl divide-y divide-hairline-soft">
      {/* Section header */}
      <div className="pb-5">
        <h3 className="text-[15px] font-[600] text-ink">{t('agentBehaviour')}</h3>
        <p className="mt-1 text-xs text-text-muted">
          {t('agentBehaviourHint')}
        </p>
      </div>

      {/* Mode */}
      <div className={row}>
        <div>
          <p className={label}>
            <Settings2 className="w-4 h-4 text-accent-cobalt" strokeWidth={2} />
            {t('mode')}
          </p>
          <p className={`mt-1 ${hint}`}>
            {t('modeHint')}
          </p>
        </div>
        <SegmentedControl value={currentMode} options={MODE_OPTIONS} onChange={setMode} />
      </div>

      {/* Approval / Autonomy */}
      <div className={row}>
        <div>
          <p className={label}>
            <Lock className="w-4 h-4 text-accent-cobalt" strokeWidth={2} />
            {t('approval')}
          </p>
          <p className={`mt-1 ${hint}`}>
            {t('approvalHint')} <strong>{t('approvalAutoLabel')}</strong> {t('approvalAutoHint')}
          </p>
        </div>
        <SegmentedControl value={currentAutonomy} options={AUTONOMY_OPTIONS} onChange={setAutonomy} />
      </div>

      {/* Thinking level */}
      <div className={row}>
        <div>
          <p className={label}>
            <Brain className="w-4 h-4 text-accent-cobalt" strokeWidth={2} />
            {t('thinking')}
          </p>
          <p className={`mt-1 ${hint}`}>
            {t('thinkingHint')}
          </p>
        </div>
        <SegmentedControl value={currentThinking} options={THINKING_OPTIONS} onChange={setThinking} />
      </div>

      {/* Language */}
      <div className={row}>
        <div>
          <p className={label}>
            <Globe className="w-4 h-4 text-accent-cobalt" strokeWidth={2} />
            {t('language')}
          </p>
        </div>
        <LanguageSwitcher />
      </div>
    </div>
  );
}
