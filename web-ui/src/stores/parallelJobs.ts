import { create } from 'zustand';
import { wsClient } from '../api/websocket';
import type {
  ParallelSolverStartedData,
  ParallelSolverProgressData,
  ParallelSolverDoneData,
} from '../types';

export interface ThreadState {
  thread: number;
  status: 'running' | 'done' | 'dropped';
  ok?: boolean;
  summary?: string;
  winner?: boolean;
}

export interface ParallelJob {
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

interface ParallelJobsState {
  jobs: Record<string, ParallelJob>;
  order: string[];
  clear(): void;
}

export const useParallelJobsStore = create<ParallelJobsState>((set) => ({
  jobs: {},
  order: [],
  clear: () => set({ jobs: {}, order: [] }),
}));

// ─── WS subscriptions — register once at module load ─────────────────────────

let _initialized = false;

export function initParallelJobsStore() {
  if (_initialized) return;
  _initialized = true;

  wsClient.on('parallel_solver_started', (msg) => {
    const data = msg.data as ParallelSolverStartedData;
    const now = Date.now();
    const job: ParallelJob = {
      jobId: data.job_id,
      task: data.task,
      n: data.n,
      status: 'running',
      done: 0,
      threads: Array.from({ length: data.n }, (_, i) => ({ thread: i, status: 'running' as const })),
      startedAt: now,
      updatedAt: now,
    };
    useParallelJobsStore.setState((state) => {
      const order = state.order.includes(data.job_id)
        ? state.order
        : [data.job_id, ...state.order];
      return {
        jobs: { ...state.jobs, [data.job_id]: job },
        order,
      };
    });
  });

  wsClient.on('parallel_solver_progress', (msg) => {
    const data = msg.data as ParallelSolverProgressData;
    useParallelJobsStore.setState((state) => {
      const job = state.jobs[data.job_id];
      if (!job) return state;
      return {
        jobs: {
          ...state.jobs,
          [data.job_id]: { ...job, done: data.done, updatedAt: Date.now() },
        },
      };
    });
  });

  wsClient.on('parallel_solver_done', (msg) => {
    const data = msg.data as ParallelSolverDoneData;
    useParallelJobsStore.setState((state) => {
      const job = state.jobs[data.job_id];
      if (!job) return state;

      const droppedSet = new Set(data.dropped_threads ?? []);
      const candidateMap = new Map(
        (data.candidates ?? []).map((c) => [c.thread, c])
      );

      const threads: ThreadState[] = job.threads.map((t) => {
        if (droppedSet.has(t.thread)) {
          return { ...t, status: 'dropped' as const };
        }
        const candidate = candidateMap.get(t.thread);
        return {
          ...t,
          status: 'done' as const,
          ok: candidate?.ok,
          summary: candidate?.summary,
          winner: t.thread === data.winner_thread,
        };
      });

      const updated: ParallelJob = {
        ...job,
        status: 'done',
        applied: data.applied,
        winnerThread: data.winner_thread,
        reasoning: data.reasoning,
        conflictedFiles: data.conflicted_files ?? [],
        droppedThreads: data.dropped_threads ?? [],
        threads,
        updatedAt: Date.now(),
      };

      return { jobs: { ...state.jobs, [data.job_id]: updated } };
    });
  });
}

// Self-init at module load — mirrors how chat.ts registers its handlers at the top level.
initParallelJobsStore();
