import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

interface Props { url: string; name: string }

export function ImageViewer({ url, name }: Props) {
  const { t } = useTranslation('artifacts');
  const [zoom, setZoom] = useState(1);
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-hairline-soft/60 bg-surface-soft/30">
        <button
          onClick={() => setZoom(z => Math.max(0.1, z - 0.25))}
          aria-label={t('imageViewer.zoomOut')}
          className="p-1 rounded text-ink/65 hover:text-ink hover:bg-surface-soft cursor-pointer transition-colors"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={() => setZoom(1)}
          aria-label={t('imageViewer.resetZoom')}
          className="p-1 rounded text-ink/65 hover:text-ink hover:bg-surface-soft cursor-pointer transition-colors"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
        <button
          onClick={() => setZoom(z => Math.min(8, z + 0.25))}
          aria-label={t('imageViewer.zoomIn')}
          className="p-1 rounded text-ink/65 hover:text-ink hover:bg-surface-soft cursor-pointer transition-colors"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <span className="ml-2 rounded-md bg-surface-soft px-2 py-0.5 text-[11px] font-mono text-text-muted">{Math.round(zoom * 100)}%</span>
      </div>
      <div className="flex-1 overflow-auto flex items-center justify-center bg-surface-soft/70">
        <img
          src={url}
          alt={name}
          style={{ transform: `scale(${zoom})`, transformOrigin: 'center' }}
          className="max-w-full max-h-full object-contain"
        />
      </div>
    </div>
  );
}
