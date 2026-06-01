import { createFileRoute, useParams } from "@tanstack/react-router";
import { Activity, LayoutDashboard, Mail, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/components/stat-card";
import { findTenant, useMe } from "@/lib/me-adapter";

export const Route = createFileRoute("/_app/workspace/$workspaceId/")({
  component: WorkspaceOverview,
});

function WorkspaceOverview() {
  const { workspaceId } = useParams({ from: "/_app/workspace/$workspaceId/" });
  const { me } = useMe();
  const t = findTenant(me, workspaceId);
  return (
    <>
      <PageHeader
        title={t?.name ?? "Workspace"}
        description="An at-a-glance overview of this workspace. Live metrics arrive as your team gets going."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard icon={Users} label="Members" />
        <StatCard icon={Mail} label="Pending invites" />
        <StatCard icon={Activity} label="Recent activity" />
      </div>
      <EmptyState
        icon={LayoutDashboard}
        title="Your workspace is ready"
        description="Use the sidebar to manage Members, Roles, the Audit log and Settings. Activity and member growth will surface here as the team grows."
      />
    </>
  );
}
