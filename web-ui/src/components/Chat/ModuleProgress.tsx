import type { Message } from '../../types';

/**
 * Live progress for a streaming service-module tool call. Rendered from
 * `module_progress` WS events (see minder/core/modules/remote.py `_run_stream`),
 * updated in place, and replaced by the module's card when the tool finishes.
 */
export function ModuleProgress({ message }: { message: Message }) {
  const pct = typeof message.progress_pct === 'number' ? message.progress_pct : null;
  const label = message.progress_message || 'Working…';
  return (
    <div className="mx-4 my-2 rounded-md bg-bg-100/50 border border-border-300/15 px-3 py-2.5">
      <div className="flex items-center gap-2">
        <div className="w-3.5 h-3.5 border-[1.5px] border-accent-secondary-100/60 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        {message.progress_module && (
          <span className="text-[10px] font-mono uppercase tracking-wide text-text-400">
            {message.progress_module}
          </span>
        )}
        <span className="text-sm text-text-200 truncate flex-1">{label}</span>
        {pct !== null && <span className="text-xs font-mono text-text-400">{Math.round(pct)}%</span>}
      </div>
      {pct !== null && (
        <div className="mt-2 h-1 rounded-full bg-bg-300/40 overflow-hidden">
          <div
            className="h-full bg-accent-secondary-100 transition-all duration-slow"
            style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
          />
        </div>
      )}
    </div>
  );
}
