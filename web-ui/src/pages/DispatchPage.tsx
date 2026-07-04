import { useState, useEffect, useRef } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { Eyebrow } from '../components/ui/Eyebrow';
import { useSolverJobsStore, solverStatusCounts } from '../stores/solverJobs';
import type {
  SolverJob,
  DivideJobView,
  DivideTaskView,
  ParallelJobView,
  ThreadState,
  BBNote,
} from '../stores/solverJobs';

// ─── Notes stream ─────────────────────────────────────────────────────────────

const NOTE_COLOR: Record<string, string> = {
  fact: 'text-text-secondary',
  question: 'text-amber-400',
  decision: 'text-semantic-success',
  blocker: 'text-semantic-danger',
};

function NoteLine({ note, pulse }: { note: BBNote; pulse: boolean }) {
  const color = NOTE_COLOR[note.type] ?? 'text-text-400';
  return (
    <div
      className={`text-[11px] font-mono truncate ${color} ${pulse ? 'animate-note-pulse motion-reduce:animate-none' : ''}`}
      title={`${note.type}: ${note.content}`}
    >
      <span className="opacity-60 mr-1">[{note.type}]</span>
      {note.content}
    </div>
  );
}

function NotesStream({
  notes,
  hiddenWhenPending,
  status,
}: {
  notes: BBNote[];
  hiddenWhenPending?: boolean;
  status?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const prev = useRef(notes.length);
  const isNew = notes.length > prev.current;
  useEffect(() => {
    prev.current = notes.length;
  }, [notes.length]);

  if (notes.length === 0 && (hiddenWhenPending || status === 'pending')) return null;
  if (notes.length === 0) return null;

  const visible = expanded ? notes : notes.slice(-3);
  const hidden = notes.length - visible.length;
  return (
    <div className="ml-16 mr-4 pb-2 space-y-0.5">
      {visible.map((n, i) => (
        <NoteLine
          key={`${n.ts}-${i}`}
          note={n}
          pulse={isNew && i === visible.length - 1}
        />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="text-[10px] font-mono text-text-500 hover:text-text-300 transition-colors"
          aria-label={`Show ${hidden} more notes`}
        >
          … {hidden} more
        </button>
      )}
      {expanded && notes.length > 3 && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="text-[10px] font-mono text-text-500 hover:text-text-300 transition-colors"
        >
          collapse
        </button>
      )}
    </div>
  );
}

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

// ─── Status badges ────────────────────────────────────────────────────────────

const JOB_STATUS_CONFIG = {
  running: { color: 'text-amber-400', bg: 'bg-amber-400/10', dot: 'bg-amber-400', label: 'Running' },
  done:    { color: 'text-semantic-success', bg: 'bg-semantic-success/10', dot: 'bg-semantic-success', label: 'Done' },
  failed:  { color: 'text-semantic-danger', bg: 'bg-semantic-danger/10', dot: 'bg-semantic-danger', label: 'Failed' },
} as const;

const TASK_STATUS_CONFIG = {
  pending: { color: 'text-text-muted', bg: 'bg-text-muted/10', dot: 'bg-text-muted', label: 'Pending', strike: false },
  running: { color: 'text-amber-400', bg: 'bg-amber-400/10', dot: 'bg-amber-400', label: 'Running', strike: false },
  done:    { color: 'text-semantic-success', bg: 'bg-semantic-success/10', dot: 'bg-semantic-success', label: 'Done', strike: false },
  failed:  { color: 'text-semantic-danger', bg: 'bg-semantic-danger/10', dot: 'bg-semantic-danger', label: 'Failed', strike: false },
  skipped: { color: 'text-text-muted', bg: 'bg-text-muted/10', dot: 'bg-text-muted', label: 'Skipped', strike: true },
} as const;

const THREAD_STATUS_CONFIG = {
  running: { color: 'text-amber-400', bg: 'bg-amber-400/10', dot: 'bg-amber-400', label: 'Running' },
  done:    { color: 'text-semantic-success', bg: 'bg-semantic-success/10', dot: 'bg-semantic-success', label: 'Done' },
  dropped: { color: 'text-semantic-danger', bg: 'bg-semantic-danger/10', dot: 'bg-semantic-danger', label: 'Dropped' },
} as const;

function Badge({
  cfg,
}: {
  cfg: { color: string; bg: string; dot: string; label: string };
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm text-[11px] font-mono font-[500] ${cfg.color} ${cfg.bg}`}
      aria-label={cfg.label}
    >
      {cfg.label}
    </span>
  );
}

/** Compact "1m 12s" / "8s" duration between two epoch-ms timestamps. */
function fmtDuration(fromMs: number, toMs: number): string {
  const s = Math.max(0, Math.round((toMs - fromMs) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

/** Uppercase status pill — the wireframe's dispatch task chip. */
function StatusChip({ cfg }: { cfg: { color: string; bg: string; label: string } }) {
  return (
    <span
      className={`inline-flex items-center flex-shrink-0 text-[10px] font-mono font-semibold uppercase tracking-[0.08em] px-2 py-0.5 rounded-full ${cfg.color} ${cfg.bg}`}
    >
      {cfg.label}
    </span>
  );
}

/** Bordered mono pill for the module / strategy label on a task row. */
function MetaPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex-shrink-0 max-w-[150px] truncate text-[11px] font-mono text-text-secondary px-2 py-0.5 rounded-full border border-hairline-soft/25 whitespace-nowrap">
      {children}
    </span>
  );
}

/** Module pill + progress bar + percent label — the wireframe's task progress row. */
function ProgressRow({
  pill,
  pct,
  fill,
  ariaNow,
  ariaMax,
}: {
  pill: React.ReactNode;
  pct: number;
  fill: string;
  ariaNow: number;
  ariaMax: number;
}) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div className="flex items-center gap-3">
      {pill}
      <div
        className="flex-1 h-1.5 bg-surface-soft rounded-full overflow-hidden"
        role="progressbar"
        aria-valuenow={ariaNow}
        aria-valuemin={0}
        aria-valuemax={ariaMax}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-slow ease-motion-out ${fill}`}
          style={{ width: `${Math.max(clamped, 2)}%` }}
        />
      </div>
      <span className="w-10 flex-shrink-0 text-right text-[13px] font-mono tabular-nums text-text-secondary">
        {Math.round(clamped)}%
      </span>
    </div>
  );
}

// ─── Divide card ────────────────────────────────────────────────────────────

function TaskRow({ task }: { task: DivideTaskView }) {
  const isSkipped = task.status === 'skipped';
  return (
    <>
      <div className="flex items-start gap-3 px-4 py-2 border-t border-border-300/10 transition-colors duration-150 hover:bg-bg-100/30">
        <span className={`font-mono text-[11px] text-text-400 mt-0.5 w-16 flex-shrink-0 ${isSkipped ? 'line-through opacity-50' : ''}`}>
          {task.id}
        </span>
        <Badge cfg={TASK_STATUS_CONFIG[task.status]} />
        <div className="flex-1 min-w-0 space-y-0.5">
          <span className={`block text-xs text-text-300 truncate ${isSkipped ? 'line-through opacity-50' : ''}`} title={task.description}>
            {task.description}
          </span>
          {task.depends_on.length > 0 && (
            <span className="text-[11px] font-mono text-text-500 truncate block">
              &larr; {task.depends_on.join(', ')}
            </span>
          )}
          {task.status === 'done' && task.result && (
            <span className="block text-[11px] text-text-400 truncate" title={task.result}>
              {task.result}
            </span>
          )}
        </div>
      </div>
      <NotesStream notes={task.notes ?? []} status={task.status} />
    </>
  );
}

function DivideCard({ job }: { job: DivideJobView }) {
  const statusCfg = JOB_STATUS_CONFIG[job.status];
  const total = job.tasks.length;
  const done = job.tasks.filter(
    (t) => t.status === 'done' || t.status === 'failed' || t.status === 'skipped',
  ).length;
  const pct = total ? Math.max((done / total) * 100, 3) : 3;
  return (
    <div
      className="bg-bg-000 border border-border-300/15 rounded-md overflow-hidden transition-shadow duration-300 hover:shadow-hover focus-visible:outline-none focus-visible:shadow-focus-ring"
      role="region"
      tabIndex={0}
      aria-label={`Divide job ${job.jobId.slice(0, 8)}, ${done} of ${total} tasks done`}
    >
      <div className="px-4 py-3.5">
        <div className="flex items-center gap-2.5 mb-3">
          <span className="text-text-400"><IconDivide /></span>
          <StatusChip cfg={statusCfg} />
          <p className="flex-1 min-w-0 text-sm text-text-100 font-[500] truncate" title={job.request}>
            {job.request}
          </p>
          <span className="flex-shrink-0 text-[11px] font-mono text-text-500" title="Tasks done · elapsed">
            {done}/{total} · {fmtDuration(job.startedAt, job.updatedAt)}
          </span>
        </div>
        <ProgressRow
          pill={<MetaPill>{job.module}</MetaPill>}
          pct={pct}
          fill={statusCfg.dot}
          ariaNow={done}
          ariaMax={total}
        />
      </div>

      <div>
        {job.tasks.map((t) => (
          <TaskRow key={t.id} task={t} />
        ))}
      </div>

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

// ─── Parallel card ──────────────────────────────────────────────────────────

function ThreadRow({ thread }: { thread: ThreadState }) {
  return (
    <>
      <div className="flex items-start gap-3 px-4 py-2 border-t border-border-300/10 transition-colors hover:bg-bg-100/30">
        <span className="font-mono text-[11px] text-text-400 mt-0.5 w-16 flex-shrink-0">
          Thread {thread.thread}
        </span>
        <Badge cfg={THREAD_STATUS_CONFIG[thread.status]} />
        {thread.summary && (
          <span className="flex-1 text-xs text-text-300 truncate min-w-0" title={thread.summary}>
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
      <NotesStream notes={thread.notes ?? []} />
    </>
  );
}

function ParallelCard({ job }: { job: ParallelJobView }) {
  const overallStatus = job.status === 'running' ? 'running' : 'done';
  const statusCfg = THREAD_STATUS_CONFIG[overallStatus];
  return (
    <div
      className="bg-bg-000 border border-border-300/15 rounded-md overflow-hidden transition-shadow duration-fast hover:shadow-hover"
      role="region"
      aria-label={`Parallel job ${job.jobId.slice(0, 8)}`}
    >
      <div className="px-4 py-3.5">
        <div className="flex items-center gap-2.5 mb-3">
          <span className="text-text-400"><IconBranch /></span>
          <StatusChip cfg={statusCfg} />
          <p className="flex-1 min-w-0 text-sm text-text-100 font-[500] truncate" title={job.task}>
            {job.task}
          </p>
          <span className="flex-shrink-0 text-[11px] font-mono text-text-500" title="Solvers done · elapsed">
            {job.done}/{job.n} · {fmtDuration(job.startedAt, job.updatedAt)}
          </span>
        </div>
        <ProgressRow
          pill={<MetaPill>parallel</MetaPill>}
          pct={job.n > 0 ? (job.done / job.n) * 100 : 0}
          fill={statusCfg.dot}
          ariaNow={job.done}
          ariaMax={job.n}
        />
      </div>

      <div>
        {job.threads.map((t) => (
          <ThreadRow key={t.thread} thread={t} />
        ))}
      </div>

      {job.status === 'done' && (
        <div className="px-4 py-3 border-t border-border-300/10 space-y-2 bg-bg-100/20">
          <div className="flex items-center gap-2">
            {job.applied ? (
              <span className="flex items-center gap-1.5 text-semantic-success text-xs font-mono">
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
          {job.reasoning && (
            <p className="text-xs text-text-300 leading-relaxed">
              <span className="font-mono text-text-500 mr-1">Judge:</span>
              {job.reasoning}
            </p>
          )}
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

function JobCard({ job }: { job: SolverJob }) {
  return job.strategy === 'divide' ? <DivideCard job={job} /> : <ParallelCard job={job} />;
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-6 text-center">
      <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true" className="text-text-500 mb-4">
        <circle cx="20" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
        <path d="M20 12V20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M20 20L10 28" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M20 20L30 28" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="10" cy="32" r="4" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="30" cy="32" r="4" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <p className="text-sm text-text-300 font-[330] max-w-xs">
        No dispatch jobs yet.{' '}
        <span className="font-mono text-text-400">Run solve</span>{' '}
        with strategy <span className="font-mono text-text-400">divide</span> or{' '}
        <span className="font-mono text-text-400">parallel</span> to fan out work.
      </p>
    </div>
  );
}

// ─── Summary cards ──────────────────────────────────────────────────────────
// Dot colors mirror the status configs above: running→amber, queued→neutral
// (pending/skipped's text-500), done→emerald.

const SUMMARY_CARDS = [
  { key: 'running', label: 'Running', dot: 'bg-amber-400' },
  { key: 'queued', label: 'Queued', dot: 'bg-text-muted' },
  { key: 'done', label: 'Done', dot: 'bg-semantic-success' },
] as const;

function SummaryCards({
  counts,
}: {
  counts: { running: number; queued: number; done: number };
}) {
  return (
    <dl className="grid grid-cols-3 divide-x divide-hairline-soft/15 rounded-md border border-hairline-soft/15 bg-canvas overflow-hidden mb-8">
      {SUMMARY_CARDS.map(({ key, label }) => {
        const live = key === 'running' && counts.running > 0;
        return (
          <div key={key} className="relative px-5 py-4">
            {live && (
              <span
                aria-hidden="true"
                className="absolute inset-x-0 top-0 h-px bg-amber-400/60"
              />
            )}
            <dd
              className={`text-[34px] leading-none font-[340] tabular-nums tracking-[-0.02em] ${
                counts[key] > 0 ? 'text-ink' : 'text-text-muted'
              }`}
            >
              {counts[key]}
            </dd>
            <dt className="mt-2.5 flex items-center gap-2">
              <span className="text-[11px] font-mono uppercase tracking-[0.12em] text-text-muted">
                {label}
              </span>
            </dt>
          </div>
        );
      })}
    </dl>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function DispatchPage() {
  const jobs = useSolverJobsStore((s) => s.jobs);
  const order = useSolverJobsStore((s) => s.order);
  const clear = useSolverJobsStore((s) => s.clear);
  const counts = useSolverJobsStore(useShallow(solverStatusCounts));

  return (
    <div className="flex-1 min-h-0 overflow-y-auto bg-canvas">
      <main>
        <div className="max-w-content mx-auto px-6 py-8">
          <div className="flex items-start justify-between gap-4 mb-8">
            <div className="min-w-0">
              <Eyebrow as="p" className="mb-2.5 text-ink/45">Dispatch · background tasks</Eyebrow>
              <div className="flex items-center gap-3">
                <h1 className="text-[32px] font-[600] leading-none text-ink tracking-[-0.6px]">
                  Dispatch
                </h1>
                {counts.running > 0 && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-400/10 px-2.5 py-1 text-[11px] font-mono font-[500] text-amber-400">
                    {counts.running} live
                  </span>
                )}
              </div>
              <p className="text-body-sm text-ink/60 mt-2 max-w-[62ch]">
                Live task dispatch — divide (DAG decomposition) and parallel
                (worktree-isolated solvers, judged and applied) in one view.
              </p>
            </div>

            {order.length > 0 && (
              <button
                onClick={clear}
                className="flex-shrink-0 px-3 py-1.5 text-[13px] font-mono text-ink/55 hover:text-ink hover:bg-surface-soft rounded-md transition-colors duration-fast cursor-pointer focus-visible:outline-none focus-visible:shadow-focus-ring"
                aria-label="Clear all jobs"
              >
                Clear
              </button>
            )}
          </div>

          <SummaryCards counts={counts} />

          {order.length === 0 ? (
            <EmptyState />
          ) : (
            <div className="space-y-4">
              {order.map((jobId, i) => {
                const job = jobs[jobId];
                if (!job) return null;
                return (
                  <div
                    key={jobId}
                    className="animate-reveal motion-reduce:animate-none"
                    style={{ animationDelay: `${Math.min(i, 6) * 50}ms` }}
                  >
                    <JobCard job={job} />
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
