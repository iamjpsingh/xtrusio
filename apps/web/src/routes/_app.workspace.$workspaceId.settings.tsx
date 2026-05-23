import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceSettingsPage } from "@/components/workspace-settings-page";

export const Route = createFileRoute("/_app/workspace/$workspaceId/settings")({
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/settings",
  });
  return <WorkspaceSettingsPage workspaceId={workspaceId} />;
}
