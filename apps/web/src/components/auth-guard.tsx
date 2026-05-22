import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";
import { fetchMe } from "@/lib/api";
import { resolveRoute } from "@/lib/route-resolver";

export function AuthGuard({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const navigate = useNavigate();
  // Subscribe to router state so AuthGuard re-renders on navigation — useRouter()
  // alone returns the router instance and does NOT subscribe to state changes,
  // so a stale pathname would persist after navigate() fires (the bug surfaced
  // by P6b's more aggressive resolveRoute, which redirects super_admin away from
  // /sign-in instead of always rendering it).
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !!auth.session,
    refetchOnWindowFocus: false,
  });

  const decision = resolveRoute({ session: auth.session ? "s" : null, me: me ?? null }, pathname);

  useEffect(() => {
    if (decision.kind === "redirect" && pathname !== decision.to) {
      navigate({ to: decision.to });
    }
  }, [decision, pathname, navigate]);

  if (auth.loading || (auth.session && meLoading)) {
    return (
      <div className="grid min-h-screen place-items-center text-muted-foreground">Loading…</div>
    );
  }
  if (decision.kind === "redirect") return null;
  return <>{children}</>;
}
