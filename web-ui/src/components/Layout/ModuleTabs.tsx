import { motion, useReducedMotion } from 'motion/react';
import { cn } from '../../lib/cn';
import { useModulesStore } from '../../stores/modules';

/**
 * ModuleTabs — the active module's declared sub-views, rendered as a top-bar
 * tab row. Renders nothing when no module is selected or the module ships no
 * tabs (single-view modules keep their existing single-dashboard behavior).
 */
export function ModuleTabs() {
  const activeName = useModulesStore((s) => s.activeModuleDashboard);
  const modules = useModulesStore((s) => s.modulesWithDashboards);
  const activeTab = useModulesStore((s) => s.activeModuleTab);
  const setModuleTab = useModulesStore((s) => s.setModuleTab);
  const reduce = useReducedMotion();

  const mod = activeName ? modules.find((m) => m.name === activeName) : null;
  if (!mod || mod.tabs.length === 0) return null;

  return (
    <nav aria-label="Module views" className="inline-flex items-center gap-4">
      {mod.tabs.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => setModuleTab(tab.id)}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'relative inline-flex items-center h-8 pb-0.5 text-[13px] font-[480]',
              'tracking-[-0.1px] select-none cursor-pointer transition-colors duration-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/30',
              'focus-visible:ring-offset-1 focus-visible:ring-offset-canvas rounded-sm',
              active ? 'text-ink' : 'text-ink/55 hover:text-ink',
            )}
          >
            <span>{tab.label}</span>
            {active && (
              <motion.span
                layoutId="moduletabs-active"
                className="absolute inset-x-0 -bottom-0.5 h-0.5 rounded-md bg-ink"
                transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 480, damping: 34 }}
                aria-hidden="true"
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}
