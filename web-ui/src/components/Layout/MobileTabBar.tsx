import { MessageSquare, FolderTree, FileText } from 'lucide-react';

export type MobilePanel = 'chat' | 'files' | 'editor';

const TABS: { id: MobilePanel; label: string; Icon: typeof MessageSquare }[] = [
  { id: 'chat', label: 'Chat', Icon: MessageSquare },
  { id: 'files', label: 'Files', Icon: FolderTree },
  { id: 'editor', label: 'Editor', Icon: FileText },
];

/**
 * MobileTabBar — the phone bottom navigation. On small screens the desktop's
 * three columns collapse to one panel at a time; these tabs switch between
 * Chat, Files and Editor. Hidden at md+ where the columns coexist.
 */
export function MobileTabBar({
  active,
  onChange,
}: {
  active: MobilePanel;
  onChange: (panel: MobilePanel) => void;
}) {
  return (
    <nav
      aria-label="Panels"
      className="flex-shrink-0 flex border-t border-hairline-soft bg-canvas pb-[max(0.5rem,env(safe-area-inset-bottom))]"
    >
      {TABS.map(({ id, label, Icon }) => {
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
            {label}
          </button>
        );
      })}
    </nav>
  );
}
