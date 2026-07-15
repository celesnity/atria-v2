import { MessageSquare, Package, FolderTree, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export type MobilePanel = 'chat' | 'module' | 'files' | 'editor';

/**
 * MobileTabBar — the phone bottom navigation. On small screens the desktop's
 * columns collapse to one panel at a time; these tabs switch between
 * Chat, Module, Files and Editor. Hidden at md+ where the columns coexist.
 */
export function MobileTabBar({
  active,
  onChange,
}: {
  active: MobilePanel;
  onChange: (panel: MobilePanel) => void;
}) {
  const { t } = useTranslation('layout');

  const TABS: { id: MobilePanel; labelKey: string; Icon: typeof MessageSquare }[] = [
    { id: 'chat', labelKey: 'mobileTabBar.chat', Icon: MessageSquare },
    { id: 'module', labelKey: 'mobileTabBar.module', Icon: Package },
    { id: 'files', labelKey: 'mobileTabBar.files', Icon: FolderTree },
    { id: 'editor', labelKey: 'mobileTabBar.editor', Icon: FileText },
  ];

  return (
    <nav
      aria-label={t('mobileTabBar.ariaLabel')}
      className="flex-shrink-0 flex border-t border-hairline-soft bg-canvas pb-[max(0.5rem,env(safe-area-inset-bottom))]"
    >
      {TABS.map(({ id, labelKey, Icon }) => {
        const isActive = active === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onChange(id)}
            aria-current={isActive ? 'page' : undefined}
            className={`flex-1 flex flex-col items-center gap-1 pt-2 pb-1 text-[11px] cursor-pointer transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-accent-main-100 ${
              isActive
                ? 'text-accent-main-100 font-[600]'
                : 'text-ink/50 hover:text-ink/80'
            }`}
          >
            <Icon className="w-5 h-5" strokeWidth={1.75} />
            {t(labelKey)}
          </button>
        );
      })}
    </nav>
  );
}
