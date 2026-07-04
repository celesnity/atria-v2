import { useEffect, useMemo, useState, Suspense, lazy } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Eye, FileCode2 } from 'lucide-react';
import { apiClient } from '../../../api/client';
import { fsScopeKey, type FsScope } from '../../../types';

const MonacoViewer = lazy(() =>
  import('./MonacoViewer').then(m => ({ default: m.MonacoViewer })),
);

interface Props { scope: FsScope; path: string; editable?: boolean; convId?: string; tabId?: string }

export function MarkdownViewer({ scope, path, editable, convId, tabId }: Props) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'preview' | 'source'>('preview');
  const scopeKey = useMemo(() => fsScopeKey(scope), [scope]);

  useEffect(() => {
    let cancelled = false;
    setText(null);
    setError(null);
    apiClient.readFsText(scope, path)
      .then(t => { if (!cancelled) setText(t); })
      .catch(e => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [scopeKey, path]);

  if (error) return <div className="p-4 text-xs font-mono text-block-coral">Failed to load file: {error}</div>;
  if (text === null) return <div className="p-4 text-xs font-mono text-ink/45">Loading…</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-2 py-1.5 border-b border-hairline-soft/60 bg-surface-soft/30">
        <div className="inline-flex items-center gap-0.5 rounded-md border border-hairline-soft/40 bg-surface-soft/40 p-0.5">
          <button
            onClick={() => setMode('preview')}
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[12px] font-mono rounded-[4px] cursor-pointer transition-all duration-fast ${
              mode === 'preview' ? 'bg-canvas text-ink shadow-soft' : 'text-text-muted hover:text-ink'
            }`}
          >
            <Eye className="w-3 h-3" /> Preview
          </button>
          <button
            onClick={() => setMode('source')}
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[12px] font-mono rounded-[4px] cursor-pointer transition-all duration-fast ${
              mode === 'source' ? 'bg-canvas text-ink shadow-soft' : 'text-text-muted hover:text-ink'
            }`}
          >
            <FileCode2 className="w-3 h-3" /> Source
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {mode === 'preview' ? (
          <div className="prose prose-invert max-w-none p-4 text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        ) : (
          <Suspense fallback={<div className="p-4 text-xs font-mono text-ink/45">Loading editor…</div>}>
            <MonacoViewer scope={scope} path={path} languageOverride="markdown" editable={editable} convId={convId} tabId={tabId} />
          </Suspense>
        )}
      </div>
    </div>
  );
}
