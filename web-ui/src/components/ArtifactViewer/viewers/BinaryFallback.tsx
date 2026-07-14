import { File as FileIcon, Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Props {
  path: string;
  size?: number;
  url: string;
}

function formatSize(n?: number): string {
  if (n == null) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export function BinaryFallback({ path, size, url }: Props) {
  const { t } = useTranslation('artifacts');
  const name = path.split('/').pop() ?? path;
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 p-6 select-none">
      <div className="relative grid h-16 w-16 place-items-center">
        <span
          aria-hidden
          className="absolute inset-0 rounded-md bg-gradient-brand opacity-20 blur-xl"
        />
        <span className="relative grid h-12 w-12 place-items-center rounded-xl border border-hairline-soft/40 bg-surface-soft/60 text-text-secondary">
          <FileIcon className="w-5 h-5" />
        </span>
      </div>
      <p className="font-mono text-sm text-ink">{name}</p>
      {size !== undefined && <p className="font-mono text-xs text-text-muted">{formatSize(size)}</p>}
      <a
        href={url}
        download={name}
        className="mt-1 inline-flex items-center gap-1.5 rounded-md bg-gradient-brand px-3 py-1.5 text-xs font-medium text-white shadow-glow-accent transition-all duration-base ease-motion-spring hover:-translate-y-px cursor-pointer"
      >
        <Download className="w-3.5 h-3.5" /> {t('binaryFallback.download')}
      </a>
    </div>
  );
}
