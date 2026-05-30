// apps/web/src/lib/session-cache.ts
// Module-level cached Supabase session (L10). Subscribing once to
// onAuthStateChange means apiFetch reads the access token from memory instead
// of calling getSession() 4–8x per page load.
//
// Lifecycle note (spec §8.5): before the first auth-state event fires, the
// cache is `undefined` (distinct from `null` = "known signed out"). apiFetch
// falls back to a one-time getSession() in that window. After the first event,
// the cache stays current for the lifetime of the tab.

import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";

let currentSession: Session | null | undefined = undefined;

supabase.auth.onAuthStateChange((_event, session) => {
  currentSession = session;
});

/**
 * Read the cached session. Returns `undefined` only in the brief pre-first-event
 * window; callers (apiFetch) must fall back to `supabase.auth.getSession()` then.
 */
export function getCachedSession(): Session | null | undefined {
  return currentSession;
}

/** Resolve a session, preferring the cache and falling back to getSession(). */
export async function resolveSession(): Promise<Session | null> {
  if (currentSession !== undefined) return currentSession;
  const {
    data: { session },
  } = await supabase.auth.getSession();
  // Populate the cache so subsequent calls in the same window don't re-hit it.
  currentSession = session;
  return session;
}
