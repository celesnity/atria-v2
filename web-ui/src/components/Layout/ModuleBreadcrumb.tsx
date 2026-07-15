import { ChevronDown, Package } from 'lucide-react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useModulesStore } from '../../stores/modules';
import { useModuleHealth } from '../../hooks/useModuleHealth';
import { ModuleHealthDot } from './ModuleHealthDot';

/**
 * ModuleBreadcrumb — top-bar module picker. Shows the active module and opens
 * a dropdown of all modules with dashboards. Replaces the old sidebar Modules
 * list; selecting a module drives the center + ModuleTabs.
 */
export function ModuleBreadcrumb() {
  const { t } = useTranslation('layout');
  const modules = useModulesStore((s) => s.modulesWithDashboards);
  const activeName = useModulesStore((s) => s.activeModuleDashboard);
  const openDashboard = useModulesStore((s) => s.openDashboard);
  const refresh = useModulesStore((s) => s.refresh);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  // Connector health per service module, polled on mount + every ~30s.
  const moduleHealth = useModuleHealth();

  // Populate the module list on startup.
  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('mousedown', onDown);
    return () => window.removeEventListener('mousedown', onDown);
  }, [open]);

  if (modules.length === 0) return null;
  const active = modules.find((m) => m.name === activeName) ?? null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 h-8 px-2 rounded-md text-[13px] font-[480] text-ink/80 hover:bg-surface-soft hover:text-ink transition-colors cursor-pointer"
      >
        {active?.icon_url ? (
          <img src={active.icon_url} className="h-4 w-4" alt="" />
        ) : (
          <Package className="h-4 w-4 text-ink/50" strokeWidth={1.5} />
        )}
        <span className="truncate max-w-[160px]">{active?.display_name ?? t('moduleBreadcrumb.selectModule')}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: reduce ? 0 : 0.16, ease: [0.16, 1, 0.3, 1] }}
            style={{ transformOrigin: 'top left' }}
            className="absolute left-0 top-full z-50 mt-2 w-64 max-h-80 overflow-y-auto rounded-md border border-hairline-soft bg-canvas shadow-modal py-1"
          >
            {modules.map((m) => {
              const isActive = m.name === activeName;
              return (
                <button
                  key={m.name}
                  role="menuitem"
                  type="button"
                  onClick={() => {
                    openDashboard(m.name);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors ${
                    isActive ? 'bg-surface-soft text-ink' : 'text-ink/75 hover:bg-surface-soft hover:text-ink'
                  }`}
                >
                  {m.icon_url ? (
                    <img src={m.icon_url} className="h-4 w-4 flex-shrink-0" alt="" />
                  ) : (
                    <Package className="h-4 w-4 flex-shrink-0 text-ink/40" strokeWidth={1.5} />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-[480]">{m.display_name}</span>
                    {m.tooltip && m.tooltip !== m.display_name && (
                      <span className="block truncate text-[11px] text-ink/45">{m.tooltip}</span>
                    )}
                  </span>
                  <ModuleHealthDot status={moduleHealth[m.name]} />
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
