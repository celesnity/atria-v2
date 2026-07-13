/**
 * Settings Modal with Vertical Sidebar Navigation
 *
 * Redesigned to use vertical tabs for better space utilization
 * and scalability as more settings categories are added.
 */

import { useState, useEffect } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import {
  CpuChipIcon,
  ServerIcon,
  Cog6ToothIcon,
  SparklesIcon,
  ChatBubbleLeftRightIcon,
  WrenchScrewdriverIcon
} from '@heroicons/react/24/outline';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { ModelSettings } from './ModelSettings';
import { MCPSettings } from './MCPSettings';
import { PersonasSettings } from './PersonasSettings';
import { ChannelSettings } from './ChannelSettings';
import { ToolsSettings } from './ToolsSettings';
import { GeneralSettings } from './GeneralSettings';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type TabId = 'model' | 'mcp' | 'tools' | 'connect' | 'personas' | 'general';

interface TabConfig {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const tabs: TabConfig[] = [
  {
    id: 'model',
    label: 'Model',
    icon: CpuChipIcon,
    description: 'Configure AI model and provider settings'
  },
  {
    id: 'mcp',
    label: 'MCP Servers',
    icon: ServerIcon,
    description: 'Manage Model Context Protocol servers'
  },
  {
    id: 'tools',
    label: 'Tools',
    icon: WrenchScrewdriverIcon,
    description: 'Enable or disable individual agent tools to trim context'
  },
  {
    id: 'connect',
    label: 'Connect',
    icon: ChatBubbleLeftRightIcon,
    description: 'Connect Telegram & other chat apps to the agent'
  },
  {
    id: 'personas',
    label: 'Personas',
    icon: SparklesIcon,
    description: 'Customize agent behavior and system prompts'
  },
  {
    id: 'general',
    label: 'General',
    icon: Cog6ToothIcon,
    description: 'General application settings'
  },
];

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>('model');
  const reduce = useReducedMotion();

  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  const activeTabConfig = tabs.find(t => t.id === activeTab);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
          className="fixed inset-0 z-50 flex items-stretch sm:items-center justify-center bg-black/60 backdrop-blur-sm sm:p-4"
          onClick={onClose}
        >
          <motion.div
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.97 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="relative bg-canvas sm:rounded-lg shadow-modal w-full sm:max-w-content h-full sm:h-[85vh] flex flex-col overflow-hidden sm:border border-hairline-soft">
        {/* Ambient brand wash bleeding down from the header — barely-there depth. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-32 opacity-[0.06]"
          style={{ background: 'radial-gradient(120% 100% at 20% 0%, hsl(221 83% 53%), transparent 70%)' }}
        />

        {/* Header */}
        <div className="relative flex items-center justify-between px-5 sm:px-7 py-4 border-b border-hairline-soft">
          <div className="min-w-0">
            <h2 className="text-[22px] leading-none font-[600] tracking-[-0.02em] text-gradient-brand">
              Settings
            </h2>
            {activeTabConfig && (
              <p className="mt-1.5 text-xs text-text-muted truncate">{activeTabConfig.description}</p>
            )}
          </div>
          <button
            aria-label="Close dialog"
            onClick={onClose}
            className="flex-shrink-0 grid h-9 w-9 place-items-center rounded-md text-text-muted transition-all hover:bg-surface-soft hover:text-ink active:scale-95"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Main Content Area with Sidebar (horizontal tab bar on mobile) */}
        <div className="relative flex-1 flex flex-col sm:flex-row overflow-hidden min-h-0">
          {/* Navigation — vertical sidebar at sm+, horizontal scroll bar on mobile */}
          <div className="flex-shrink-0 w-full sm:w-60 border-b sm:border-b-0 sm:border-r border-hairline-soft bg-surface-soft/40 overflow-x-auto sm:overflow-y-auto sm:flex sm:flex-col">
            <nav className="flex sm:flex-col gap-1 p-2.5 sm:p-3 sm:flex-1">
              {tabs.map(tab => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;

                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`group relative flex-shrink-0 sm:w-full flex items-center gap-2.5 sm:gap-3 pl-3.5 pr-3 py-2 sm:py-2.5 rounded-md text-left whitespace-nowrap cursor-pointer transition-colors duration-200 ${
                      isActive ? 'text-ink' : 'text-text-secondary hover:text-ink'
                    }`}
                  >
                    {/* Shared-element active surface — slides between tabs. */}
                    {isActive && (
                      <motion.span
                        layoutId="settingsActiveTab"
                        aria-hidden
                        className="absolute inset-0 rounded-md bg-gradient-to-r from-accent-cobalt/[0.14] to-accent-violet/[0.08] ring-1 ring-inset ring-accent-cobalt/20"
                        transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                      />
                    )}
                    {/* Accent rail — desktop only, animates with the surface. */}
                    {isActive && (
                      <motion.span
                        layoutId="settingsActiveRail"
                        aria-hidden
                        className="absolute left-0 top-1/2 hidden sm:block h-5 w-[3px] -translate-y-1/2 rounded-r-pill bg-gradient-brand"
                        transition={{ type: 'spring', stiffness: 420, damping: 34 }}
                      />
                    )}
                    <Icon className={`relative z-10 w-[18px] h-[18px] flex-shrink-0 transition-colors ${isActive ? 'text-accent-cobalt' : 'text-text-muted group-hover:text-text-secondary'}`} />
                    <span className="relative z-10 text-sm font-[540] tracking-[-0.01em]">{tab.label}</span>
                  </button>
                );
              })}
            </nav>

            {/* Sidebar Footer — hidden on the mobile horizontal bar */}
            <div className="hidden sm:flex items-center gap-2 px-4 py-3.5 border-t border-hairline-soft/70">
              <span className="grid h-5 w-5 place-items-center rounded-[5px] bg-gradient-brand text-[10px] font-[700] text-white shadow-glow-accent">A</span>
              <p className="text-[11px] font-mono text-text-muted">Minder v0.1.7</p>
            </div>
          </div>

          {/* Content Area */}
          <div className="flex-1 min-w-0 overflow-y-auto bg-canvas">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={reduce ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                className="p-5 sm:p-7"
              >
                {activeTab === 'model' && <ModelSettings />}
                {activeTab === 'mcp' && <MCPSettings />}
                {activeTab === 'tools' && <ToolsSettings />}
                {activeTab === 'connect' && <ChannelSettings />}
                {activeTab === 'personas' && <PersonasSettings />}
                {activeTab === 'general' && <GeneralSettings />}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        {/* Footer */}
        <div className="relative flex items-center justify-between gap-3 px-5 sm:px-7 py-3.5 border-t border-hairline-soft bg-surface-soft/40">
          <p className="hidden sm:block text-[11px] text-text-muted">
            <kbd className="rounded border border-hairline-soft bg-canvas px-1.5 py-0.5 font-mono text-[10px]">Esc</kbd> to close
          </p>
          <button
            onClick={onClose}
            className="ml-auto rounded-pill bg-gradient-brand px-5 py-2 text-sm font-[540] text-white shadow-glow-nebula transition-all hover:brightness-110 active:scale-[0.97]"
          >
            Done
          </button>
        </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
