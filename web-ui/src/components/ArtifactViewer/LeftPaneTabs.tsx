import { useLocalStorage } from 'usehooks-ts';

export type LeftMode = 'files' | 'modules';

interface Props {
  mode: LeftMode;
  onChange: (m: LeftMode) => void;
}

export function LeftPaneTabs({ mode, onChange }: Props) {
  const btn = (m: LeftMode, label: string) => (
    <button
      key={m}
      onClick={() => onChange(m)}
      className={[
        'relative px-2.5 py-1 text-xs font-mono rounded-[7px] transition-all duration-fast cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-cobalt',
        mode === m
          ? 'bg-canvas text-ink shadow-soft'
          : 'text-text-muted hover:text-ink',
      ].join(' ')}
    >
      {label}
    </button>
  );
  return (
    <div className="flex items-center border-b border-hairline-soft/60 px-2 py-1.5 flex-shrink-0">
      <div className="inline-flex items-center gap-0.5 rounded-md border border-hairline-soft/40 bg-surface-soft/40 p-0.5">
        {btn('files', 'Files')}
        {btn('modules', 'Modules')}
      </div>
    </div>
  );
}

export function useLeftMode() {
  return useLocalStorage<LeftMode>('artifact-viewer.left-mode', 'files');
}
