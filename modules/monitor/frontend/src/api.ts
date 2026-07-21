import { useCallback, useEffect, useRef, useState } from "react";

export interface ToolState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  status: "initial_loading" | "live" | "stale" | "offline";
  refreshedAt: Date | null;
  refresh: () => Promise<void>;
}

function reportsDisconnected(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, any>;
  if (data.connected === false) return true;
  const source = data.source_health || data.sources?.[0];
  return source?.connected === false || source?.status === "disconnected" || data.overall_status === "disconnected";
}

export async function invokeTool<T>(apiBase: string, tool: string, args: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch(`${apiBase.replace(/\/$/, "")}/connector/tools/${tool}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ arguments: args }),
  });
  const envelope = await response.json();
  if (!response.ok || envelope.success === false) {
    throw new Error(envelope.error?.message || envelope.output || `Monitor request failed (${response.status})`);
  }
  return envelope.output as T;
}

export function useTool<T>(
  apiBase: string,
  tool: string,
  args: Record<string, unknown> = {},
  refreshMs = 4000,
): ToolState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const [status, setStatus] = useState<ToolState<T>["status"]>("initial_loading");
  const inFlight = useRef(false);
  const dataRef = useRef<T | null>(null);
  const argsRef = useRef(JSON.stringify(args));
  argsRef.current = JSON.stringify(args);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const next = await invokeTool<T>(apiBase, tool, JSON.parse(argsRef.current));
      dataRef.current = next;
      setData(next);
      setError(null);
      setRefreshedAt(new Date());
      setStatus(reportsDisconnected(next) ? "offline" : "live");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Monitor is unavailable.");
      setStatus(dataRef.current === null ? "offline" : "stale");
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }, [apiBase, tool]);

  useEffect(() => {
    void refresh();
    if (refreshMs <= 0) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, refreshMs);
    return () => window.clearInterval(timer);
  }, [refresh, refreshMs]);

  return { data, error, loading, status, refreshedAt, refresh };
}
