// apps/web/src/lib/session-cache.ts
//
// Session access for apiFetch, backed by the Zustand auth store (the single
// source of truth — lib/auth-store.ts). There is no separate onAuthStateChange
// subscription here anymore; the store owns it, so apiFetch always reads the
// same session the rest of the app sees.
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import { useAuthStore } from "./auth-store";

/** Current session snapshot from the store (null when signed out / pre-init). */
export function getCachedSession(): Session | null {
  return useAuthStore.getState().session;
}

/**
 * Resolve a session for apiFetch — prefer the store, and fall back to a one-shot
 * getSession() only during the brief pre-init "loading" window (before the
 * store's first auth event has landed).
 */
export async function resolveSession(): Promise<Session | null> {
  const { session, status } = useAuthStore.getState();
  if (status !== "loading") return session;
  const {
    data: { session: fresh },
  } = await supabase.auth.getSession();
  return fresh;
}
