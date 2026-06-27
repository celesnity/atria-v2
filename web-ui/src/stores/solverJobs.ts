import { create } from 'zustand';
import { wsClient } from '../api/websocket';
import type {
  ParallelSolverProgressData,
  ParallelSolverDoneData,
} from '../types';

// ─── Divide (DAG decomposition) shapes ───────────────────────────────────────

export interface DivideTaskView {
  id: string;
  description: string;
  depends_on: string[];
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  result?: string;
}

export interface DivideJobView {
  strategy: 'divide';
  jobId: string;
  module: string;
  request: string;
  tasks: DivideTaskView[];
  status: 'running' | 'done' | 'failed';
  summary?: string;
  startedAt: number;
  updatedAt: number;
}

// ─── Parallel (worktree fan-out + judge) shapes ──────────────────────────────

export interface ThreadState {
  thread: number;
  status: 'running' | 'done' | 'dropped';
  ok?: boolean;
  summary?: string;
  winner?: boolean;
}

export interface ParallelJobView {
  strategy: 'parallel';
  jobId: string;
  task: string;
  n: number;
  status: 'running' | 'done';
  done: number;
  threads: ThreadState[];
  applied?: boolean;
  winnerThread?: number;
  reasoning?: string;
  conflictedFiles?: string[];
  droppedThreads?: number[];
  startedAt: number;
  updatedAt: number;
}

/** A single dispatched solve job, discriminated by `strategy`. */
export type SolverJob = DivideJobView | ParallelJobView;

interface SolverJobsState {
  jobs: Record<string, SolverJob>;
  order: string[];
  clear(): void;
}

export const useSolverJobsStore = create<SolverJobsState>((set) => ({
  jobs: {},
  order: [],
  clear: () => set({ jobs: {}, order: [] }),
}));

/** Count of jobs still running — used for the nav activity badge. */
export function runningSolverCount(state: SolverJobsState): number {
  return Object.values(state.jobs).filter((j) => j.status === 'running').length;
}

// ─── WS subscriptions — register once at module load ─────────────────────────

let _initialized = false;

function upsertOrder(order: string[], jobId: string): string[] {
  return order.includes(jobId) ? order : [jobId, ...order];
}

export function initSolverJobsStore() {
  if (_initialized) return;
  _initialized = true;

  // ── started ──────────────────────────────────────────────────────────────
  wsClient.on('solver_started', (msg) => {
    const data = msg.data as { strategy: 'divide' | 'parallel'; job_id: string } & Record<
      string,
      unknown
    >;
    const now = Date.now();
    let job: SolverJob;

    if (data.strategy === 'divide') {
      const d = data as unknown as {
        job_id: string;
        module: string;
        request: string;
        tasks: { id: string; description: string; depends_on: string[] }[];
      };
      job = {
        strategy: 'divide',
        jobId: d.job_id,
        module: d.module,
        request: d.request,
        tasks: d.tasks.map((t) => ({
          id: t.id,
          description: t.description,
          depends_on: t.depends_on,
          status: 'pending',
        })),
        status: 'running',
        startedAt: now,
        updatedAt: now,
      };
    } else {
      const p = data as unknown as { job_id: string; task: string; n: number };
      job = {
        strategy: 'parallel',
        jobId: p.job_id,
        task: p.task,
        n: p.n,
        status: 'running',
        done: 0,
        threads: Array.from({ length: p.n }, (_, i) => ({
          thread: i,
          status: 'running' as const,
        })),
        startedAt: now,
        updatedAt: now,
      };
    }

    useSolverJobsStore.setState((state) => ({
      jobs: { ...state.jobs, [data.job_id]: job },
      order: upsertOrder(state.order, data.job_id),
    }));
  });

  // ── progress ─────────────────────────────────────────────────────────────
  wsClient.on('solver_progress', (msg) => {
    const data = msg.data as { strategy: 'divide' | 'parallel'; job_id: string } & Record<
      string,
      unknown
    >;
    useSolverJobsStore.setState((state) => {
      const job = state.jobs[data.job_id];
      if (!job) return state;

      if (job.strategy === 'divide' && data.strategy === 'divide') {
        const d = data as unknown as {
          task_id: string;
          status: DivideTaskView['status'];
          result?: string;
        };
        const tasks = job.tasks.map((t) =>
          t.id === d.task_id ? { ...t, status: d.status, result: d.result } : t
        );
        return {
          jobs: {
            ...state.jobs,
            [data.job_id]: { ...job, tasks, updatedAt: Date.now() },
          },
        };
      }

      if (job.strategy === 'parallel' && data.strategy === 'parallel') {
        const p = data as unknown as ParallelSolverProgressData;
        return {
          jobs: {
            ...state.jobs,
            [data.job_id]: { ...job, done: p.done, updatedAt: Date.now() },
          },
        };
      }

      return state;
    });
  });

  // ── done ─────────────────────────────────────────────────────────────────
  wsClient.on('solver_done', (msg) => {
    const data = msg.data as { strategy: 'divide' | 'parallel'; job_id: string } & Record<
      string,
      unknown
    >;
    useSolverJobsStore.setState((state) => {
      const job = state.jobs[data.job_id];
      if (!job) return state;

      if (job.strategy === 'divide' && data.strategy === 'divide') {
        const d = data as unknown as { status: 'done' | 'failed'; summary: string };
        return {
          jobs: {
            ...state.jobs,
            [data.job_id]: {
              ...job,
              status: d.status,
              summary: d.summary,
              updatedAt: Date.now(),
            },
          },
        };
      }

      if (job.strategy === 'parallel' && data.strategy === 'parallel') {
        const p = data as unknown as ParallelSolverDoneData;
        const droppedSet = new Set(p.dropped_threads ?? []);
        const candidateMap = new Map((p.candidates ?? []).map((c) => [c.thread, c]));
        const threads: ThreadState[] = job.threads.map((t) => {
          if (droppedSet.has(t.thread)) return { ...t, status: 'dropped' as const };
          const candidate = candidateMap.get(t.thread);
          return {
            ...t,
            status: 'done' as const,
            ok: candidate?.ok,
            summary: candidate?.summary,
            winner: t.thread === p.winner_thread,
          };
        });
        return {
          jobs: {
            ...state.jobs,
            [data.job_id]: {
              ...job,
              status: 'done',
              applied: p.applied,
              winnerThread: p.winner_thread,
              reasoning: p.reasoning,
              conflictedFiles: p.conflicted_files ?? [],
              droppedThreads: p.dropped_threads ?? [],
              threads,
              updatedAt: Date.now(),
            },
          },
        };
      }

      return state;
    });
  });
}

// Self-init at module load — mirrors how the previous per-strategy stores did.
initSolverJobsStore();
