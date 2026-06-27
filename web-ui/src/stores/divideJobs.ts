import { create } from 'zustand';
import { wsClient } from '../api/websocket';

export interface DivideTaskView {
  id: string;
  description: string;
  depends_on: string[];
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  result?: string;
}

export interface DivideJobView {
  jobId: string;
  module: string;
  request: string;
  tasks: DivideTaskView[];
  status: 'running' | 'done' | 'failed';
  summary?: string;
  startedAt: number;
  updatedAt: number;
}

interface DivideJobsState {
  jobs: Record<string, DivideJobView>;
  order: string[];
  clear(): void;
}

export const useDivideJobsStore = create<DivideJobsState>((set) => ({
  jobs: {},
  order: [],
  clear: () => set({ jobs: {}, order: [] }),
}));

// ─── WS subscriptions — register once at module load ─────────────────────────

let _initialized = false;

export function initDivideJobsStore() {
  if (_initialized) return;
  _initialized = true;

  wsClient.on('divide_job_started', (msg) => {
    const data = msg.data as {
      job_id: string;
      module: string;
      request: string;
      tasks: { id: string; description: string; depends_on: string[] }[];
      session_id: string;
    };
    const now = Date.now();
    const job: DivideJobView = {
      jobId: data.job_id,
      module: data.module,
      request: data.request,
      tasks: data.tasks.map((t) => ({
        id: t.id,
        description: t.description,
        depends_on: t.depends_on,
        status: 'pending',
      })),
      status: 'running',
      startedAt: now,
      updatedAt: now,
    };
    useDivideJobsStore.setState((state) => {
      const order = state.order.includes(data.job_id)
        ? state.order
        : [data.job_id, ...state.order];
      return {
        jobs: { ...state.jobs, [data.job_id]: job },
        order,
      };
    });
  });

  wsClient.on('divide_task_update', (msg) => {
    const data = msg.data as {
      job_id: string;
      task_id: string;
      status: DivideTaskView['status'];
      result?: string;
      session_id: string;
    };
    useDivideJobsStore.setState((state) => {
      const job = state.jobs[data.job_id];
      if (!job) return state;
      const tasks = job.tasks.map((t) =>
        t.id === data.task_id
          ? { ...t, status: data.status, result: data.result }
          : t
      );
      return {
        jobs: {
          ...state.jobs,
          [data.job_id]: { ...job, tasks, updatedAt: Date.now() },
        },
      };
    });
  });

  wsClient.on('divide_job_done', (msg) => {
    const data = msg.data as {
      job_id: string;
      status: 'done' | 'failed';
      summary: string;
      session_id: string;
    };
    useDivideJobsStore.setState((state) => {
      const job = state.jobs[data.job_id];
      if (!job) return state;
      return {
        jobs: {
          ...state.jobs,
          [data.job_id]: {
            ...job,
            status: data.status,
            summary: data.summary,
            updatedAt: Date.now(),
          },
        },
      };
    });
  });
}

// Self-init at module load — mirrors how parallelJobs.ts registers its handlers at the top level.
initDivideJobsStore();
