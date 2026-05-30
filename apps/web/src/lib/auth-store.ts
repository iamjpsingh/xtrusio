// apps/web/src/lib/auth-store.ts
//
// Single source of truth for the Supabase session, held in a Zustand store.
//
// Why a store instead of useEffect + useState inside a provider: the session is
// read from many places (apiFetch, AuthGuard, route gating). A store has ONE
// module-level subscription to onAuthStateChange and exposes the current value
// via getState() — so there are NO stale closures (the bug that wiped the app
// to "Loading…" on every tab switch), no effect-dependency juggling, and no
// per-component re-syncing. Components subscribe with the useAuthStore hook and
// re-render only when the slice they read changes.
import type { Session } from "@supabase/supabase-js";
import { create } from "zustand";
import { supabase } from "./supabase";
import { queryClient } from "./query-client";
import { clearLastWorkspace } from "./last-workspace";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";

export type AuthStoreState = {
  session: Session | null;
  userId: string | null;
  status: AuthStatus;
};

export const useAuthStore = create<AuthStoreState>()(() => ({
  session: null,
  userId: null,
  status: "loading",
}));

/**
 * Apply an auth change to the store. Cache is dropped ONLY on a real sign-out
 * or a genuine user *switch* — never on the SIGNED_IN / TOKEN_REFRESHED events
 * Supabase fires on tab focus, because we read the previous user id from
 * getState() (always current) rather than a stale closure.
 */
function applyAuthChange(session: Session | null, event?: string): void {
  const prevUserId = useAuthStore.getState().userId;
  const nextUserId = session?.user.id ?? null;

  if (event === "SIGNED_OUT") {
    queryClient.clear();
    clearLastWorkspace();
  } else if (prevUserId !== null && nextUserId !== null && prevUserId !== nextUserId) {
    // Different user signed in on this machine — drop the prior user's cache.
    queryClient.clear();
  }

  useAuthStore.setState({
    session,
    userId: nextUserId,
    status: session ? "authenticated" : "unauthenticated",
  });
}

let initialized = false;

/** Wire the store to Supabase auth. Idempotent — safe under React StrictMode. */
export function initAuth(): void {
  if (initialized) return;
  initialized = true;

  supabase.auth
    .getSession()
    .then(({ data }) => applyAuthChange(data.session))
    .catch((err: unknown) => {
      // Corrupted Supabase localStorage / decryption failure must not hang the
      // app on "loading" forever — treat it as signed-out.
      console.warn("getSession failed", err);
      applyAuthChange(null);
    });

  supabase.auth.onAuthStateChange((event, session) => applyAuthChange(session, event));
}
