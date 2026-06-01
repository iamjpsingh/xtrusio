import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceOverviewPage } from "@/components/workspace-overview-page";

export const Route = createFileRoute("/_app/workspace/$workspaceId/")({
  component: WorkspaceOverviewRoute,
});

function WorkspaceOverviewRoute() {
  const { workspaceId } = useParams({ from: "/_app/workspace/$workspaceId/" });
  return <WorkspaceOverviewPage workspaceId={workspaceId} />;
}
