import { LayoutList } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '../../lib/cn';
import { runningSolverCount, useSolverJobsStore } from '../../stores/solverJobs';

/**
 * BlackboardEntry — app-level top-bar link to the Blackboard monitor. Kept
 * separate from the module breadcrumb so the two navigation axes (modules vs
 * the helper monitor) stay distinct. Carries the running-jobs badge.
 */
export function BlackboardEntry() {
  const running = useSolverJobsStore(runningSolverCount);
  const active = useLocation().pathname.startsWith('/blackboard');
  return (
    <Link
      to="/blackboard"
      aria-label={running > 0 ? `Blackboard, ${running} running` : 'Blackboard'}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-[13px] font-[480]',
        'transition-colors cursor-pointer',
        active ? 'bg-surface-soft text-ink' : 'text-ink/60 hover:bg-surface-soft hover:text-ink',
      )}
    >
      <LayoutList className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" />
      <span className="hidden lg:inline">Blackboard</span>
      {running > 0 && (
        <span
          className="ml-0.5 inline-flex items-center px-1.5 h-4 rounded-md bg-amber-400/15 text-amber-500 text-[10px] font-mono font-[600] leading-none"
          aria-hidden="true"
        >
          {running}
        </span>
      )}
    </Link>
  );
}
