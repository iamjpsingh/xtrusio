import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceRolesPage } from "@/components/workspace-roles-page";

export const Route = createFileRoute("/_app/workspace/$workspaceId/roles")({
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/roles",
  });
  return <WorkspaceRolesPage workspaceId={workspaceId} />;
}
