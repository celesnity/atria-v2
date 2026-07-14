export const MAX_VALUE_CHARS = 32768;

export interface DataEntry {
  name: string;
  description?: string;
  value: unknown;
}

export interface ActionEntry {
  name: string;
  description?: string;
  onAct: () => void | Promise<void>;
}

export interface SnapshotDataEntry {
  name: string;
  description?: string;
  value: unknown;
  truncated?: boolean;
}

export interface UiSnapshot {
  page: string | null;
  data: SnapshotDataEntry[];
  actions: { name: string; description?: string }[];
}

export interface Registry {
  setPage(name: string | null): void;
  getPage(): string | null;
  setData(entry: DataEntry): void;
  removeData(name: string): void;
  setAction(entry: ActionEntry): void;
  removeAction(name: string): void;
  run(name: string): boolean;
  snapshot(): UiSnapshot;
  subscribe(fn: () => void): () => void;
}

function capValue(d: DataEntry): SnapshotDataEntry {
  let serialized: string;
  try {
    serialized = JSON.stringify(d.value) ?? '';
  } catch {
    serialized = String(d.value);
  }
  if (serialized.length > MAX_VALUE_CHARS) {
    return {
      name: d.name,
      description: d.description,
      value: serialized.slice(0, MAX_VALUE_CHARS),
      truncated: true,
    };
  }
  return { name: d.name, description: d.description, value: d.value };
}

export function createRegistry(): Registry {
  let page: string | null = null;
  const data = new Map<string, DataEntry>();
  const actions = new Map<string, ActionEntry>();
  const listeners = new Set<() => void>();
  const emit = (): void => {
    listeners.forEach((l) => l());
  };

  return {
    setPage(name) {
      page = name;
      emit();
    },
    getPage() {
      return page;
    },
    setData(entry) {
      data.set(entry.name, entry);
      emit();
    },
    removeData(name) {
      if (data.delete(name)) emit();
    },
    setAction(entry) {
      actions.set(entry.name, entry);
      emit();
    },
    removeAction(name) {
      if (actions.delete(name)) emit();
    },
    run(name) {
      const a = actions.get(name);
      if (!a) {
        console.warn(`[agent] act on unknown action: ${name}`);
        return false;
      }
      try {
        void a.onAct();
      } catch (e) {
        console.error(`[agent] onAct failed: ${name}`, e);
      }
      return true;
    },
    snapshot() {
      return {
        page,
        data: [...data.values()].map(capValue),
        actions: [...actions.values()].map((a) => ({ name: a.name, description: a.description })),
      };
    },
    subscribe(fn) {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
  };
}
