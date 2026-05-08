import { type ReactNode } from "react";
import { Navigate, useRouterState } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";

const PUBLIC_ROUTES = new Set<string>(["/sign-in"]);

export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const { location } = useRouterState();
  const isPublic = PUBLIC_ROUTES.has(location.pathname);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    );
  }
  if (!user && !isPublic) {
    return <Navigate to="/sign-in" />;
  }
  if (user && isPublic) {
    return <Navigate to="/" />;
  }
  return <>{children}</>;
}
