import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceAuditLogPage } from "@/components/workspace-audit-log-page";

export const Route = createFileRoute(
  "/_app/workspace/$workspaceId/audit-log",
)({
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/audit-log",
  });
  return <WorkspaceAuditLogPage workspaceId={workspaceId} />;
}
