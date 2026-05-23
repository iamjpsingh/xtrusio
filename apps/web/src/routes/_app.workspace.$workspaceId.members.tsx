import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceMembersPage } from "@/components/workspace-members-page";

export const Route = createFileRoute("/_app/workspace/$workspaceId/members")({
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/members",
  });
  return <WorkspaceMembersPage workspaceId={workspaceId} />;
}
