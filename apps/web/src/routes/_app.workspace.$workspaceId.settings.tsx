import { createFileRoute } from "@tanstack/react-router";
import { Settings } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/settings")({
  component: WorkspaceSettingsPage,
});

function WorkspaceSettingsPage() {
  return (
    <>
      <PageHeader
        title="Workspace settings"
        description="Per-workspace configuration. Visible to anyone with workspace.settings.read."
      />
      <EmptyState
        icon={Settings}
        title="Settings ship in P6c"
        description="Backed by /api/workspaces/$wid/settings."
      />
    </>
  );
}
