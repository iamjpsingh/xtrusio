import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useRouter } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";
import { fetchMe } from "@/lib/api";
import { resolveRoute } from "@/lib/route-resolver";

export function AuthGuard({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const navigate = useNavigate();
  const pathname = router.state.location.pathname;

  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !!auth.session,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const decision = resolveRoute(
    { session: auth.session ? "s" : null, me: me ?? null },
    pathname,
  );

  useEffect(() => {
    if (decision.kind === "redirect" && pathname !== decision.to) {
      navigate({ to: decision.to });
    }
  }, [decision, pathname, navigate]);

  if (auth.loading || (auth.session && meLoading)) {
    return (
      <div className="grid min-h-screen place-items-center text-muted-foreground">
        Loading…
      </div>
    );
  }
  if (decision.kind === "redirect") return null;
  return <>{children}</>;
}
