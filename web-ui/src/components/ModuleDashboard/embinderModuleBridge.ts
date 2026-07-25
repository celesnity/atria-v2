export type ModuleEmbinderContext = Record<string, unknown>;

type ModuleEmbinderHandler = (action: string, args: Record<string, unknown>) => Promise<unknown>;
type ContextListener = (moduleName: string, context: ModuleEmbinderContext | null) => void;

const handlers = new Map<string, ModuleEmbinderHandler>();
const contexts = new Map<string, ModuleEmbinderContext>();
const listeners = new Set<ContextListener>();
const surfaceWaiters = new Map<string, Set<(handler: ModuleEmbinderHandler) => void>>();

function notify(moduleName: string, context: ModuleEmbinderContext | null) {
  for (const listener of listeners) listener(moduleName, context);
}

export function registerModuleEmbinderSurface(
  moduleName: string,
  handler: ModuleEmbinderHandler,
): () => void {
  handlers.set(moduleName, handler);
  const waiters = surfaceWaiters.get(moduleName);
  if (waiters) {
    surfaceWaiters.delete(moduleName);
    for (const resolve of waiters) resolve(handler);
  }
  return () => {
    if (handlers.get(moduleName) !== handler) return;
    handlers.delete(moduleName);
    contexts.delete(moduleName);
    notify(moduleName, null);
  };
}

export function publishModuleEmbinderContext(
  moduleName: string,
  context: ModuleEmbinderContext,
): void {
  contexts.set(moduleName, context);
  notify(moduleName, context);
}

export function getModuleEmbinderContext(moduleName: string): ModuleEmbinderContext | null {
  return contexts.get(moduleName) ?? null;
}

export function subscribeModuleEmbinderContext(listener: ContextListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export async function callModuleEmbinderAction(
  moduleName: string,
  action: string,
  args: Record<string, unknown> = {},
): Promise<unknown> {
  let handler = handlers.get(moduleName);
  if (!handler) handler = await waitForModuleEmbinderSurface(moduleName);
  return handler(action, args);
}

function waitForModuleEmbinderSurface(moduleName: string): Promise<ModuleEmbinderHandler> {
  return new Promise((resolve, reject) => {
    const timer = globalThis.setTimeout(() => {
      const waiters = surfaceWaiters.get(moduleName);
      if (waiters) waiters.delete(onSurface);
      reject(new Error(`${moduleName} is not open or does not expose an Embinder surface.`));
    }, 5_000);
    const onSurface = (handler: ModuleEmbinderHandler) => {
      globalThis.clearTimeout(timer);
      resolve(handler);
    };
    const waiters = surfaceWaiters.get(moduleName) ?? new Set<(handler: ModuleEmbinderHandler) => void>();
    waiters.add(onSurface);
    surfaceWaiters.set(moduleName, waiters);
  });
}
