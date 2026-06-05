import { useQuery } from "@tanstack/react-query";
import { Activity, Building2, LayoutDashboard, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Forbidden } from "@/components/forbidden";
import { StatCard } from "@/components/stat-card";
import { fetchPlatformStats } from "@/lib/api";
import { isForbiddenError } from "@/lib/errors";
import { getDefaultLandingPath, useMe } from "@/lib/me-adapter";
import { qk } from "@/lib/query-keys";

/**
 * Platform dashboard — live metrics for `/platform`. One round-trip
 * (`GET /api/platform/stats`); the backend returns ONLY the metrics the caller
 * is authorized for (`null` otherwise), so each card renders only when its
 * field is non-null. Monochrome, tokens only.
 */
export function PlatformDashboardPage() {
  const { me } = useMe();
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: qk.platformStats(),
    queryFn: fetchPlatformStats,
    refetchOnWindowFocus: false,
  });

  // A 403 is not retryable — a minimal-role user simply isn't authorized to
  // read these metrics. Render the access surface (no retry) instead of an
  // <ErrorState onRetry> that would re-fire the same 403 forever. Only 5xx /
  // network failures get the retryable error state.
  const forbidden = isError && isForbiddenError(error);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="A platform-wide overview of clients, users, and recent activity."
      />
      {forbidden ? (
        <Forbidden landingPath={getDefaultLandingPath(me)} />
      ) : isError ? (
        <ErrorState
          title="Couldn't load metrics"
          description="We couldn't load the platform metrics. Check your connection and try again."
          onRetry={() => void refetch()}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(isPending || data?.client_tenants != null) && (
              <StatCard
                icon={Building2}
                label="Client tenants"
                value={
                  data?.client_tenants != null ? data.client_tenants.toLocaleString() : undefined
                }
                loading={isPending}
              />
            )}
            {(isPending || data?.active_platform_users != null) && (
              <StatCard
                icon={Users}
                label="Platform users"
                value={
                  data?.active_platform_users != null
                    ? data.active_platform_users.toLocaleString()
                    : undefined
                }
                hint="active"
                loading={isPending}
              />
            )}
            {(isPending || data?.recent_activity != null) && (
              <StatCard
                icon={Activity}
                label="Recent activity"
                value={
                  data?.recent_activity != null ? data.recent_activity.toLocaleString() : undefined
                }
                hint="last 7 days"
                loading={isPending}
              />
            )}
          </div>
          <EmptyState
            icon={LayoutDashboard}
            title="More insight is on the way"
            description="As clients onboard and teams start working, richer activity, recent runs, and tenant health will surface here."
          />
        </>
      )}
    </>
  );
}
