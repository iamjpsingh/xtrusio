// apps/web/src/lib/auth.tsx
//
// Thin React surface over the Zustand auth store (lib/auth-store.ts). The
// session itself lives in the store with a single module-level subscription;
// this file only exposes the existing `useAuth()` hook + `<AuthProvider>` so
// consumers (AuthGuard, sign-in page, user menu, __root) stay unchanged.
import { type ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import { initAuth, useAuthStore } from "./auth-store";

type AuthState = {
  user: User | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
};

// Initialise the store as soon as the auth module is first imported (once).
initAuth();

/**
 * Kept as a passthrough so the existing `<AuthProvider>` in __root.tsx and the
 * component tree are unchanged. The store self-initialises (see initAuth above),
 * so there is no provider state to hold.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

async function signIn(email: string, password: string): Promise<{ error: string | null }> {
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  return { error: error?.message ?? null };
}

async function signOut(): Promise<void> {
  await supabase.auth.signOut();
}

/** Read the current auth state from the store. Re-renders only when the
 * session/status slice changes — never on unrelated renders. */
export function useAuth(): AuthState {
  const session = useAuthStore((s) => s.session);
  const status = useAuthStore((s) => s.status);
  return {
    user: session?.user ?? null,
    session,
    loading: status === "loading",
    signIn,
    signOut,
  };
}
