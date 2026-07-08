import { X, FileText, Code2, Image as ImageIcon, BarChart3, File as FileIcon, Package } from 'lucide-react';
import { useViewerTabsStore } from '../../stores/viewerTabs';
import { pickRenderer } from './viewers/extensions';
import type { ViewerTab } from '../../types';

interface Props {
  convId: string;
  onCollapse?: () => void;
}

function iconFor(tab: ViewerTab) {
  if (tab.kind === 'module') return Package;
  const kind = pickRenderer(tab.ext);
  if (kind === 'markdown') return FileText;
  if (kind === 'monaco') return Code2;
  if (kind === 'image') return ImageIcon;
  if (kind === 'csv' || kind === 'excel') return BarChart3;
  return FileIcon;
}

export function TabBar({ convId, onCollapse: _onCollapse }: Props) {
  const slice = useViewerTabsStore(s => s.tabsByConv[convId]);
  const setActive = useViewerTabsStore(s => s.setActive);
  const closeTab = useViewerTabsStore(s => s.closeTab);

  const tabs = slice?.tabs ?? [];
  const activeId = slice?.activeId ?? null;
  const dirty = slice?.dirty ?? {};

  return (
    <div className="flex-1 flex items-center gap-0.5 overflow-x-auto px-1 py-1 min-w-0">
      {tabs.length === 0 && (
        <span className="text-[13px] font-mono text-ink/35 px-2 select-none">No file open</span>
      )}
      {tabs.map(tab => {
        const Icon = iconFor(tab);
        const isActive = tab.id === activeId;
        const isDirty = !!dirty[tab.id];
        return (
          <div
            key={tab.id}
            onClick={() => setActive(convId, tab.id)}
            onMouseDown={(e) => {
              if (e.button === 1) { e.preventDefault(); closeTab(convId, tab.id); }
            }}
            className={`group relative inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-md rounded-b-none text-[12px] font-mono cursor-pointer transition-colors whitespace-nowrap ${
              isActive
                ? 'bg-gradient-to-b from-accent-cobalt/12 to-transparent text-ink'
                : 'text-ink/55 hover:bg-surface-soft hover:text-ink/80'
            }`}
            role="tab"
            aria-selected={isActive}
            title={
              tab.kind === 'file'
                ? tab.path
                : tab.kind === 'module-file'
                  ? `${tab.module}/${tab.path}`
                  : `module: ${tab.name}`
            }
          >
            {/* Active tab spine — gradient-brand underline matching the app accent. */}
            {isActive && (
              <span
                aria-hidden
                className="absolute inset-x-0 -bottom-px h-0.5 rounded-md bg-gradient-brand"
              />
            )}
            <Icon className={`w-3 h-3 flex-shrink-0 ${isActive ? 'text-accent-cobalt' : 'text-ink/40'}`} />
            <span className="truncate max-w-[140px]">{tab.name}</span>
            {isDirty && (
              <span
                aria-label="Unsaved changes"
                title="Unsaved changes"
                className={`flex-shrink-0 text-[13px] leading-none ${
                  isActive ? 'text-accent-cobalt' : 'text-ink/50'
                }`}
              >
                *
              </span>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); closeTab(convId, tab.id); }}
              aria-label={`Close ${tab.name}`}
              className={`p-0.5 rounded hover:bg-ink/15 ${
                isActive ? 'opacity-60 hover:opacity-100' : 'opacity-0 group-hover:opacity-60'
              } transition-opacity`}
            >
              <X className="w-2.5 h-2.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
