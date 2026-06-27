import { AppNavBar } from '../components/Layout/AppNavBar';
import { useParallelJobsStore } from '../stores/parallelJobs';
import type { ParallelJob, ThreadState } from '../stores/parallelJobs';

// ─── SVG icons ────────────────────────────────────────────────────────────────

function IconBranch() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="flex-shrink-0">
      <circle cx="5" cy="3" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="5" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="11" cy="6" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M5 4.5v7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M5 4.5C5 7 11 6 11 7.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" className="flex-shrink-0">
      <path d="M2.5 7L5.5 10L11.5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconX() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" className="flex-shrink-0">
      <path d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IconStar() {
  return (
    <svg width="13" height="13" viewBox="0 0 13 13" fill="currentColor" aria-hidden="true" className="flex-shrink-0">
      <path d="M6.5 1L7.98 4.77L12 5.24L9.05 7.97L9.9 12L6.5 10.1L3.1 12L3.95 7.97L1 5.24L5.02 4.77L6.5 1Z" />
    </svg>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  running: { color: 'text-amber-400', bg: 'bg-amber-400/10', dot: 'bg-amber-400', label: 'Running' },
  done:    { color: 'text-emerald-400', bg: 'bg-emerald-400/10', dot: 'bg-emerald-500', label: 'Done' },
  dropped: { color: 'text-semantic-danger', bg: 'bg-semantic-danger/10', dot: 'bg-semantic-danger', label: 'Dropped' },
} as const;

function StatusBadge({ status }: { status: 'running' | 'done' | 'dropped' }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[11px] font-mono font-[500] ${cfg.color} ${cfg.bg}`}
      aria-label={cfg.label}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} ${status === 'running' ? 'animate-pulse-dot' : ''}`} aria-hidden="true" />
      {cfg.label}
    </span>
  );
}

// ─── Thread row ───────────────────────────────────────────────────────────────

function ThreadRow({ thread }: { thread: ThreadState }) {
  return (
    <div className="flex items-start gap-3 px-4 py-2 border-t border-border-300/10 transition-colors hover:bg-bg-100/30">
      <span className="font-mono text-[11px] text-text-400 mt-0.5 w-16 flex-shrink-0">
        Thread {thread.thread}
      </span>

      <StatusBadge status={thread.status} />

      {thread.summary && (
        <span
          className="flex-1 text-xs text-text-300 truncate min-w-0"
          title={thread.summary}
        >
          {thread.summary}
        </span>
      )}

      {thread.winner && (
        <span className="flex items-center gap-1 text-amber-400 text-[11px] font-mono font-[500] flex-shrink-0 ml-auto">
          <IconStar />
          winner
        </span>
      )}
    </div>
  );
}

// ─── Job card ─────────────────────────────────────────────────────────────────

function JobCard({ job }: { job: ParallelJob }) {
  const overallStatus = job.status === 'running' ? 'running' : 'done';
  const statusCfg = STATUS_CONFIG[overallStatus];

  return (
    <div
      className="bg-bg-000 border border-border-300/15 rounded-lg overflow-hidden transition-shadow duration-fast hover:shadow-hover"
      role="region"
      aria-label={`Parallel job ${job.jobId.slice(0, 8)}`}
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-4 py-3 border-b border-border-300/10">
        <IconBranch />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-mono text-text-400">{job.jobId.slice(0, 8)}</span>
            <StatusBadge status={overallStatus} />
            {job.status === 'running' && (
              <span className="text-[11px] font-mono text-text-500">
                {job.done}/{job.n} solvers
              </span>
            )}
          </div>
          <p
            className="text-sm text-text-100 font-[330] truncate mt-0.5"
            title={job.task}
          >
            {job.task}
          </p>
        </div>
      </div>

      {/* Progress stripe */}
      {job.status === 'running' && (
        <div className="h-0.5 bg-bg-200">
          <div
            className="h-full bg-amber-400 transition-all duration-slow"
            style={{ width: `${job.n > 0 ? Math.max((job.done / job.n) * 100, 3) : 3}%` }}
            role="progressbar"
            aria-valuenow={job.done}
            aria-valuemax={job.n}
          />
        </div>
      )}
      {job.status === 'done' && <div className={`h-0.5 ${statusCfg.dot}`} />}

      {/* Thread rows */}
      <div>
        {job.threads.map((t) => (
          <ThreadRow key={t.thread} thread={t} />
        ))}
      </div>

      {/* Done footer */}
      {job.status === 'done' && (
        <div className="px-4 py-3 border-t border-border-300/10 space-y-2 bg-bg-100/20">
          {/* Applied indicator */}
          <div className="flex items-center gap-2">
            {job.applied ? (
              <span className="flex items-center gap-1.5 text-emerald-400 text-xs font-mono">
                <IconCheck />
                <span>Applied</span>
              </span>
            ) : (
              <span className="flex items-center gap-1.5 text-semantic-danger text-xs font-mono">
                <IconX />
                <span>Not applied</span>
              </span>
            )}
          </div>

          {/* Judge reasoning */}
          {job.reasoning && (
            <p className="text-xs text-text-300 leading-relaxed">
              <span className="font-mono text-text-500 mr-1">Judge:</span>
              {job.reasoning}
            </p>
          )}

          {/* Conflicted files */}
          {job.conflictedFiles && job.conflictedFiles.length > 0 && (
            <div className="space-y-0.5">
              <p className="text-[11px] font-mono text-semantic-danger">
                {job.conflictedFiles.length} conflicted file{job.conflictedFiles.length !== 1 ? 's' : ''}
              </p>
              {job.conflictedFiles.map((f) => (
                <p key={f} className="text-[11px] font-mono text-text-400 ml-2 truncate" title={f}>
                  └ {f}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-6 text-center">
      <svg
        width="40" height="40" viewBox="0 0 40 40" fill="none"
        aria-hidden="true"
        className="text-text-500 mb-4"
      >
        <rect x="6" y="6" width="11" height="28" rx="3" stroke="currentColor" strokeWidth="1.5" />
        <rect x="23" y="6" width="11" height="28" rx="3" stroke="currentColor" strokeWidth="1.5" />
        <path d="M17 14h6M17 20h6M17 26h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <p className="text-sm text-text-300 font-[330] max-w-xs">
        No parallel solver jobs yet.{' '}
        <span className="font-mono text-text-400">Run solve_parallel</span>{' '}
        to fan out worktree-isolated solvers.
      </p>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function ParallelAgentsPage() {
  const jobs = useParallelJobsStore((s) => s.jobs);
  const order = useParallelJobsStore((s) => s.order);
  const clear = useParallelJobsStore((s) => s.clear);

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      <AppNavBar />

      <main className="flex-1 pt-14">
        <div className="max-w-content mx-auto px-6 py-8">
          {/* Page header */}
          <div className="flex items-start justify-between mb-8">
            <div>
              <h1 className="text-headline text-ink tracking-[-0.26px]">Parallel Agents</h1>
              <p className="text-body-sm text-ink/60 mt-1">
                Live status of fan-out solver jobs — worktree-isolated candidates judged and applied.
              </p>
            </div>

            {order.length > 0 && (
              <button
                onClick={clear}
                className="px-3 py-1.5 text-[13px] font-mono text-ink/60 hover:text-ink hover:bg-surface-soft rounded-md transition-colors duration-fast cursor-pointer focus-visible:outline-none focus-visible:shadow-focus-ring"
                aria-label="Clear all jobs"
              >
                Clear
              </button>
            )}
          </div>

          {/* Job list or empty state */}
          {order.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="space-y-4">
              {order.map((jobId) => {
                const job = jobs[jobId];
                if (!job) return null;
                return <JobCard key={jobId} job={job} />;
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
