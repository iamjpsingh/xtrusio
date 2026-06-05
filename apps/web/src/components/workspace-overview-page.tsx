import { useQuery } from "@tanstack/react-query";
import { Activity, LayoutDashboard, Mail, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Forbidden } from "@/components/forbidden";
import { StatCard } from "@/components/stat-card";
import { fetchWorkspaceStats } from "@/lib/api";
import { isForbiddenError } from "@/lib/errors";
import { qk } from "@/lib/query-keys";
import { findTenant, getDefaultLandingPath, useMe } from "@/lib/me-adapter";

type WorkspaceOverviewPageProps = {
  workspaceId: string;
};

/**
 * Workspace overview — live metrics for `/workspace/$id`. One round-trip
 * (`GET /api/workspaces/{id}/stats`); the backend returns ONLY the metrics the
 * caller is authorized for (`null` otherwise). A `read_only` / `editor` member
 * sees Members + Pending invites but NOT Recent activity. Monochrome, tokens
 * only.
 */
export function WorkspaceOverviewPage({ workspaceId }: WorkspaceOverviewPageProps) {
  const { me } = useMe();
  const t = findTenant(me, workspaceId);
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: qk.workspaceStats(workspaceId),
    queryFn: () => fetchWorkspaceStats(workspaceId),
    refetchOnWindowFocus: false,
  });

  // A 403 is not retryable — this member lacks `workspace.members.read`, so
  // re-firing would 403 again. Render the access surface (no retry); reserve
  // the retryable <ErrorState> for 5xx / network failures.
  const forbidden = isError && isForbiddenError(error);

  return (
    <>
      <PageHeader
        title={t?.name ?? "Workspace"}
        description="An at-a-glance overview of this workspace — members, invites, and recent activity."
      />
      {forbidden ? (
        <Forbidden landingPath={getDefaultLandingPath(me)} />
      ) : isError ? (
        <ErrorState
          title="Couldn't load metrics"
          description="We couldn't load this workspace's metrics. Check your connection and try again."
          onRetry={() => void refetch()}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(isPending || data?.members != null) && (
              <StatCard
                icon={Users}
                label="Members"
                value={data?.members != null ? data.members.toLocaleString() : undefined}
                hint="in this workspace"
                loading={isPending}
              />
            )}
            {(isPending || data?.pending_invites != null) && (
              <StatCard
                icon={Mail}
                label="Pending invites"
                value={
                  data?.pending_invites != null ? data.pending_invites.toLocaleString() : undefined
                }
                hint="awaiting acceptance"
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
            title="Your workspace is ready"
            description="Use the sidebar to manage Members, Roles, the Audit log and Settings. Activity and member growth will surface here as the team grows."
          />
        </>
      )}
    </>
  );
}
