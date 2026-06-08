import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";
import { supabase } from "@/lib/supabase";
import { fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { readLastWorkspace } from "@/lib/last-workspace";
import { resolveRoute } from "@/lib/route-resolver";
import { isSessionExpiredError } from "@/lib/errors";
import { FullScreenLoader } from "@/components/full-screen-loader";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";

export function AuthGuard({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const navigate = useNavigate();
  // Subscribe to router state so AuthGuard re-renders on navigation — useRouter()
  // alone returns the router instance and does NOT subscribe to state changes,
  // so a stale pathname would persist after navigate() fires (the bug surfaced
  // by P6b's more aggressive resolveRoute, which redirects super_admin away from
  // /sign-in instead of always rendering it).
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const {
    data: me,
    isLoading: meLoading,
    isError: meIsError,
    error: meError,
    refetch,
  } = useQuery({
    queryKey: qk.me(),
    queryFn: fetchMe,
    enabled: !!auth.session,
    refetchOnWindowFocus: false,
  });

  // L9: read the last-workspace pin once here and pass it into the pure
  // resolver, instead of the resolver reading localStorage on every render.
  const decision = resolveRoute(
    { session: auth.session ? "s" : null, me: me ?? null },
    pathname,
    readLastWorkspace(),
  );

  useEffect(() => {
    if (decision.kind === "redirect" && pathname !== decision.to) {
      navigate({ to: decision.to });
    }
  }, [decision, pathname, navigate]);

  if (auth.loading || (auth.session && meLoading)) {
    return <FullScreenLoader />;
  }

  // A live session whose `/me` FAILED must never fall through to render the
  // authed shell with no `me` — resolveRoute returns "render" for a null `me`
  // (it assumes the caller is still LOADING), so the shell would mount with no
  // identity and paint a blank page. Handle the settled-error state here:
  if (auth.session && meIsError) {
    // apiFetch's refresh-and-retry already failed and signed out, so a redirect
    // to /sign-in is imminent — show the loader rather than flash an error.
    if (isSessionExpiredError(meError)) return <FullScreenLoader />;
    // A surviving error: a dead/rejected account (deleted, disabled, not
    // provisioned → 401 even after a fresh token) or a transient 5xx/network
    // blip. Offer BOTH escapes — Retry (transient) and Sign in (dead session) —
    // never a blank page.
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
        <ErrorState
          title="We couldn't load your account"
          description="Your session may have expired, or we couldn't reach the server. Try again, or sign in."
          onRetry={() => void refetch()}
        />
        <Button
          variant="ghost"
          onClick={() => void supabase.auth.signOut().then(() => navigate({ to: "/sign-in" }))}
        >
          Sign in
        </Button>
      </div>
    );
  }

  if (decision.kind === "redirect") return null;
  return <>{children}</>;
}
