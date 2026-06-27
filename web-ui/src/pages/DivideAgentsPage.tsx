import { AppNavBar } from '../components/Layout/AppNavBar';
import { useDivideJobsStore } from '../stores/divideJobs';
import type { DivideJobView, DivideTaskView } from '../stores/divideJobs';

// ─── SVG icons ────────────────────────────────────────────────────────────────

function IconDivide() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="flex-shrink-0">
      <circle cx="8" cy="3" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 4.5V8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M8 8L4 11.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M8 8L12 11.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="4" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="12" cy="13" r="1.5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const JOB_STATUS_CONFIG = {
  running: { color: 'text-amber-400', bg: 'bg-amber-400/10', dot: 'bg-amber-400', label: 'Running' },
  done:    { color: 'text-emerald-400', bg: 'bg-emerald-400/10', dot: 'bg-emerald-500', label: 'Done' },
  failed:  { color: 'text-semantic-danger', bg: 'bg-semantic-danger/10', dot: 'bg-semantic-danger', label: 'Failed' },
} as const;

const TASK_STATUS_CONFIG = {
  pending: { color: 'text-text-500', bg: 'bg-text-500/10', dot: 'bg-text-500', label: 'Pending', strike: false },
  running: { color: 'text-amber-400', bg: 'bg-amber-400/10', dot: 'bg-amber-400', label: 'Running', strike: false },
  done:    { color: 'text-emerald-400', bg: 'bg-emerald-400/10', dot: 'bg-emerald-500', label: 'Done', strike: false },
  failed:  { color: 'text-semantic-danger', bg: 'bg-semantic-danger/10', dot: 'bg-semantic-danger', label: 'Failed', strike: false },
  skipped: { color: 'text-text-500', bg: 'bg-text-500/10', dot: 'bg-text-500', label: 'Skipped', strike: true },
} as const;

function JobStatusBadge({ status }: { status: keyof typeof JOB_STATUS_CONFIG }) {
  const cfg = JOB_STATUS_CONFIG[status];
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

function TaskStatusBadge({ status }: { status: DivideTaskView['status'] }) {
  const cfg = TASK_STATUS_CONFIG[status];
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

// ─── Task row ─────────────────────────────────────────────────────────────────

function TaskRow({ task }: { task: DivideTaskView }) {
  const isSkipped = task.status === 'skipped';
  return (
    <div className="flex items-start gap-3 px-4 py-2 border-t border-border-300/10 transition-colors duration-150 hover:bg-bg-100/30 cursor-pointer">
      <span className={`font-mono text-[11px] text-text-400 mt-0.5 w-16 flex-shrink-0 ${isSkipped ? 'line-through opacity-50' : ''}`}>
        {task.id}
      </span>

      <TaskStatusBadge status={task.status} />

      <div className="flex-1 min-w-0 space-y-0.5">
        <span
          className={`block text-xs text-text-300 truncate ${isSkipped ? 'line-through opacity-50' : ''}`}
          title={task.description}
        >
          {task.description}
        </span>

        {task.depends_on.length > 0 && (
          <span className="text-[11px] font-mono text-text-500 truncate block">
            &larr; {task.depends_on.join(', ')}
          </span>
        )}

        {task.status === 'done' && task.result && (
          <span
            className="block text-[11px] text-text-400 truncate"
            title={task.result}
          >
            {task.result}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Job card ─────────────────────────────────────────────────────────────────

function JobCard({ job }: { job: DivideJobView }) {
  const statusCfg = JOB_STATUS_CONFIG[job.status];

  return (
    <div
      className="bg-bg-000 border border-border-300/15 rounded-lg overflow-hidden transition-shadow duration-300 hover:shadow-hover cursor-pointer"
      role="region"
      aria-label={`Divide job ${job.jobId.slice(0, 8)}`}
    >
      {/* Header */}
      <div className="flex items-start gap-3 px-4 py-3 border-b border-border-300/10">
        <IconDivide />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-mono text-text-400">{job.jobId.slice(0, 8)}</span>
            <JobStatusBadge status={job.status} />
            <span className="text-[11px] font-mono text-text-500">{job.module}</span>
          </div>
          <p
            className="text-sm text-text-100 font-[330] truncate mt-0.5"
            title={job.request}
          >
            {job.request}
          </p>
        </div>
      </div>

      {/* Status stripe */}
      {job.status === 'running' && (
        <div className="h-0.5 bg-bg-200">
          <div className="h-full bg-amber-400 animate-pulse w-1/3" />
        </div>
      )}
      {job.status !== 'running' && <div className={`h-0.5 ${statusCfg.dot}`} />}

      {/* Task rows */}
      <div>
        {job.tasks.map((t) => (
          <TaskRow key={t.id} task={t} />
        ))}
      </div>

      {/* Done footer */}
      {(job.status === 'done' || job.status === 'failed') && job.summary && (
        <div className="px-4 py-3 border-t border-border-300/10 bg-bg-100/20">
          <p className="text-xs text-text-300 leading-relaxed">
            <span className="font-mono text-text-500 mr-1">Summary:</span>
            {job.summary}
          </p>
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
        <circle cx="20" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
        <path d="M20 12V20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M20 20L10 28" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M20 20L30 28" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="10" cy="32" r="4" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="30" cy="32" r="4" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <p className="text-sm text-text-300 font-[330] max-w-xs">
        No divide-work jobs yet.{' '}
        <span className="font-mono text-text-400">Run divide_work</span>{' '}
        to fan out tasks across module workers.
      </p>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function DivideAgentsPage() {
  const jobs = useDivideJobsStore((s) => s.jobs);
  const order = useDivideJobsStore((s) => s.order);
  const clear = useDivideJobsStore((s) => s.clear);

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      <AppNavBar />

      <main className="flex-1 pt-14">
        <div className="max-w-content mx-auto px-6 py-8">
          {/* Page header */}
          <div className="flex items-start justify-between mb-8">
            <div>
              <h1 className="text-headline text-ink tracking-[-0.26px]">Divide Agents</h1>
              <p className="text-body-sm text-ink/60 mt-1">
                Collaborative work-division across module workers — live DAG task tracking.
              </p>
            </div>

            {order.length > 0 && (
              <button
                onClick={clear}
                className="px-3 py-1.5 text-[13px] font-mono text-ink/60 hover:text-ink hover:bg-surface-soft rounded-md transition-colors duration-150 cursor-pointer focus-visible:outline-none focus-visible:shadow-focus-ring"
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
