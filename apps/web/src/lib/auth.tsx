import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import { queryClient } from "./query-client";
import { clearLastWorkspace } from "./last-workspace";

type AuthState = {
  user: User | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (!mounted) return;
        setSession(data.session);
        setLoading(false);
      })
      .catch((err: unknown) => {
        // M23: corrupted Supabase localStorage / decryption failure must not
        // hang the app on "Loading…" forever. Treat it as signed-out.
        console.warn("getSession failed", err);
        if (!mounted) return;
        setSession(null);
        setLoading(false);
      });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, s) => {
      // H1: drop every cached query + the last-workspace pin on sign-out so a
      // subsequent sign-in as a different user never sees the prior user's
      // `me`/lists. On a *different-user* sign-in, also clear (defense in depth).
      if (event === "SIGNED_OUT") {
        queryClient.clear();
        clearLastWorkspace();
      }
      if (event === "SIGNED_IN" && s?.user.id !== session?.user.id) {
        queryClient.clear();
      }
      setSession(s);
      setLoading(false);
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
    // Mount-once subscription: re-subscribing on every `session` change would
    // tear down + recreate the Supabase listener and re-run getSession. The
    // closure's `session?.user.id` read is an intentional "previous user" probe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user: session?.user ?? null,
      session,
      loading,
      signIn: async (email: string, password: string) => {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        return { error: error?.message ?? null };
      },
      signOut: async () => {
        await supabase.auth.signOut();
      },
    }),
    [session, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
