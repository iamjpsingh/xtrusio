import { createFileRoute, useParams } from "@tanstack/react-router";
import { LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
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
        description="Workspace overview. Activity, recent invites and member growth show up here once P6c lands."
      />
      <EmptyState
        icon={LayoutDashboard}
        title="Workspace ready"
        description="Use the sidebar to manage Members, Roles, the Audit log and Settings."
      />
    </>
  );
}
