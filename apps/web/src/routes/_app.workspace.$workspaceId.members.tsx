import { createFileRoute } from "@tanstack/react-router";
import { Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/members")({
  component: MembersPage,
});

function MembersPage() {
  return (
    <>
      <PageHeader
        title="Members"
        description="People with access to this workspace. Roles and grants are managed here."
      />
      <EmptyState
        icon={Users}
        title="Members management ships in P6c"
        description="The backend endpoints already exist — this UI consumes /api/workspaces/$wid/members in the next phase."
      />
    </>
  );
}
