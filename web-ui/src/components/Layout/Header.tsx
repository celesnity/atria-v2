import { useChatStore } from '../../stores/chat';

export function Header() {
  const isConnected = useChatStore(state => state.isConnected);

  return (
    <header className="bg-canvas/90 backdrop-blur-md border-b border-hairline-soft px-6 py-4">
      <div className="flex items-center justify-between max-w-content mx-auto">
        <div className="flex items-center gap-2.5">
          {/* Signature orbit glyph — matches the TopBar brand lockup. */}
          <span aria-hidden className="relative grid h-6 w-6 place-items-center">
            <span className="absolute inset-0 rounded-md bg-gradient-brand opacity-90" />
            <span className="absolute inset-[3px] rounded-md bg-canvas" />
            <span className="absolute right-[3px] top-[3px] h-1.5 w-1.5 rounded-md bg-gradient-brand" />
          </span>
          <div className="flex items-baseline gap-3">
            <h1 className="text-[18px] font-[600] tracking-[-0.02em] text-gradient-brand">Atria</h1>
            <span className="eyebrow-mono text-ink/40">Web Interface</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[12px] tracking-[0.01em] text-ink/60">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>
    </header>
  );
}
