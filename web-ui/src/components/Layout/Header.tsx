import { useChatStore } from '../../stores/chat';
import { BrandMark } from '../ui/Logo';

export function Header() {
  const isConnected = useChatStore(state => state.isConnected);

  return (
    <header className="bg-canvas/90 backdrop-blur-md border-b border-hairline-soft px-6 py-4">
      <div className="flex items-center justify-between max-w-content mx-auto">
        <div className="flex items-center gap-2.5">
          {/* Brand mark — the orbit-and-spark, matches the TopBar lockup. */}
          <BrandMark className="h-6 w-6 text-ink" />
          <div className="flex items-baseline gap-3">
            <h1 className="text-[18px] font-[600] tracking-[-0.02em] text-gradient-brand">Minder AI</h1>
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
