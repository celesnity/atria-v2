import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chat';

export function Header() {
  const { t } = useTranslation('layout');
  const isConnected = useChatStore(state => state.isConnected);

  return (
    <header className="bg-canvas/90 backdrop-blur-md border-b border-hairline-soft px-6 py-4">
      <div className="flex items-center justify-between max-w-content mx-auto">
        <div className="flex items-center gap-2.5">
          {/* Minder AI logo mark */}
          <img
            src="/logo.png"
            alt={t('header.brandLogoAlt')}
            className="h-7 w-7 select-none"
            draggable={false}
          />
          <div className="flex items-baseline gap-3">
            <h1 className="text-[18px] font-[600] tracking-[-0.02em] text-gradient-brand">{t('header.brandName')}</h1>
            <span className="eyebrow-mono text-ink/40">{t('header.webInterface')}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[12px] tracking-[0.01em] text-ink/60">
            {isConnected ? t('header.connected') : t('header.disconnected')}
          </span>
        </div>
      </div>
    </header>
  );
}
