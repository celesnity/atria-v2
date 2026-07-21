import { useCallback, useState } from "react";
import type { Locale } from "./i18n";

export type MonitorTheme = "light" | "dark";

function readStored<T extends string>(key: string, allowed: readonly T[]): T | null {
  try {
    const value = window.localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : null;
  } catch {
    return null;
  }
}

function store(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be disabled in a federated/sandboxed host. The in-memory choice still works.
  }
}

function initialTheme(hostTheme?: string | null): MonitorTheme {
  if (typeof window === "undefined") return hostTheme === "light" ? "light" : "dark";
  const stored = readStored("monitor-theme", ["light", "dark"] as const);
  if (stored) return stored;
  if (hostTheme === "light" || hostTheme === "dark") return hostTheme;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function initialLocale(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = readStored("monitor-lang", ["en", "vi"] as const);
  if (stored) return stored;
  return window.navigator.language.toLowerCase().startsWith("vi") ? "vi" : "en";
}

export function useMonitorPreferences(hostTheme?: string | null) {
  const [theme, setThemeState] = useState<MonitorTheme>(() => initialTheme(hostTheme));
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  const setTheme = useCallback((next: MonitorTheme) => {
    setThemeState(next);
    store("monitor-theme", next);
  }, []);
  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    store("monitor-lang", next);
  }, []);

  return { theme, locale, setTheme, setLocale };
}
