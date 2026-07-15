import { useEffect, useMemo, useState, Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Eye, FileCode2 } from 'lucide-react';
import { apiClient } from '../../../api/client';
import { fsScopeKey, type FsScope, type ViewerLocation } from '../../../types';

const MonacoViewer = lazy(() =>
  import('./MonacoViewer').then(m => ({ default: m.MonacoViewer })),
);

interface Props {
  scope: FsScope;
  path: string;
  editable?: boolean;
  convId?: string;
  tabId?: string;
  /** Reveal target — forces source mode, where Monaco highlights it. */
  location?: ViewerLocation;
}

export function MarkdownViewer({ scope, path, editable, convId, tabId, location }: Props) {
  const { t } = useTranslation('artifacts');
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'preview' | 'source'>(
    location?.text || location?.start != null ? 'source' : 'preview',
  );
  const scopeKey = useMemo(() => fsScopeKey(scope), [scope]);

  // A fresh citation click (new nonce) switches to source so the highlight shows.
  useEffect(() => {
    if (location?.nonce != null && (location.text || location.start != null)) setMode('source');
  }, [location?.nonce]);

  useEffect(() => {
    let cancelled = false;
    setText(null);
    setError(null);
    apiClient.readFsText(scope, path)
      .then(txt => { if (!cancelled) setText(txt); })
      .catch(e => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [scopeKey, path]);

  if (error) return <div className="p-4 text-xs font-mono text-block-coral">{t('markdownViewer.loadError', { error })}</div>;
  if (text === null) return <div className="p-4 text-xs font-mono text-ink/45">{t('markdownViewer.loading')}</div>;

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
            <Eye className="w-3 h-3" /> {t('markdownViewer.preview')}
          </button>
          <button
            onClick={() => setMode('source')}
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[12px] font-mono rounded-[4px] cursor-pointer transition-all duration-fast ${
              mode === 'source' ? 'bg-canvas text-ink shadow-soft' : 'text-text-muted hover:text-ink'
            }`}
          >
            <FileCode2 className="w-3 h-3" /> {t('markdownViewer.source')}
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {mode === 'preview' ? (
          <div className="prose prose-invert max-w-none p-4 text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        ) : (
          <Suspense fallback={<div className="p-4 text-xs font-mono text-ink/45">{t('markdownViewer.loadingEditor')}</div>}>
            <MonacoViewer scope={scope} path={path} languageOverride="markdown" editable={editable} convId={convId} tabId={tabId} location={location} />
          </Suspense>
        )}
      </div>
    </div>
  );
}
