// apps/web/src/lib/last-workspace.ts
// Persists the user's last-selected scope (platform sentinel or a workspace
// id) so revisits land in the right shell. Pure functions; no side effects
// at import time.

const KEY = "xtrusio.last-workspace";

/** Sentinel stored when the user's last selection was the platform shell. */
export const PLATFORM_SENTINEL = "__platform__";

export function readLastWorkspace(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function writeLastWorkspace(value: string): void {
  try {
    window.localStorage.setItem(KEY, value);
  } catch {
    /* localStorage may be disabled (Safari private mode etc.) — fail closed */
  }
}

export function clearLastWorkspace(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* see above */
  }
}
