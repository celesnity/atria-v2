import { MessageSquare, LayoutList } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "../../lib/cn";
import { runningSolverCount, useSolverJobsStore } from "../../stores/solverJobs";

/**
 * ViewSwitcher — the single source of truth for switching between the two
 * primary surfaces of the app: the Chat window and the Blackboard monitor
 * (helpers' bids and responses to broadcast requests, at /blackboard).
 *
 * Best-practice notes:
 *  - One consistent control rendered identically on every surface, so the
 *    Chat <-> Blackboard switch lives in the same place no matter where you are.
 *  - Segmented control communicates "these are mutually-exclusive views" and
 *    surfaces the active view (aria-current + visual fill) instead of burying
 *    navigation in a lone icon pill.
 *  - Live badge on Blackboard shows running jobs, so while you're chatting you
 *    can see helpers are working and jump straight to monitor them.
 *  - Keyboard accessible (real links, visible focus ring); icons carry text
 *    labels; the running count is announced via aria-label.
 */

interface ViewDef {
  to: string;
  label: string;
  Icon: typeof MessageSquare;
  /** Returns true when the current pathname belongs to this view. */
  isActive: (pathname: string) => boolean;
}

const VIEWS: ViewDef[] = [
  {
    to: "/chat",
    label: "Chat",
    Icon: MessageSquare,
    isActive: (p) => p === "/" || p.startsWith("/chat"),
  },
  {
    to: "/blackboard",
    label: "Blackboard",
    Icon: LayoutList,
    isActive: (p) =>
      p.startsWith("/blackboard") ||
      p.startsWith("/dispatch") ||
      p.startsWith("/divide") ||
      p.startsWith("/parallel"),
  },
];

export function ViewSwitcher({ className }: { className?: string }) {
  const location = useLocation();
  const runningJobs = useSolverJobsStore(runningSolverCount);
  const reduce = useReducedMotion();

  return (
    <nav
      aria-label="Primary view"
      className={cn("inline-flex items-center gap-4", className)}
    >
      {VIEWS.map(({ to, label, Icon, isActive }) => {
        const active = isActive(location.pathname);
        const isBlackboard = to === "/blackboard";
        const showBadge = isBlackboard && runningJobs > 0;
        return (
          <Link
            key={to}
            to={to}
            aria-current={active ? "page" : undefined}
            aria-label={
              showBadge ? `${label}, ${runningJobs} running` : label
            }
            className={cn(
              "relative inline-flex items-center gap-1.5 h-8 pb-0.5",
              "text-[13px] font-[480] tracking-[-0.1px] select-none cursor-pointer",
              "transition-colors duration-200",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/30 focus-visible:ring-offset-1 focus-visible:ring-offset-canvas rounded-sm",
              active ? "text-ink" : "text-ink/55 hover:text-ink",
            )}
          >
            <Icon className="w-3.5 h-3.5" strokeWidth={1.75} aria-hidden="true" />
            <span>{label}</span>
            {active && (
              <motion.span
                layoutId="viewswitcher-active"
                className="absolute inset-x-0 -bottom-0.5 h-0.5 rounded-md bg-ink"
                transition={
                  reduce
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 480, damping: 34 }
                }
                aria-hidden="true"
              />
            )}
            {showBadge && (
              <span
                className="ml-0.5 inline-flex items-center gap-1 pl-1.5 pr-1.5 h-4 rounded-md bg-amber-400/15 text-amber-500 text-[10px] font-mono font-[600] leading-none"
                aria-hidden="true"
              >
                {runningJobs}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
