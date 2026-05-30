import { createFileRoute, redirect, useParams } from "@tanstack/react-router";
import { fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { getDefaultLandingPath, hasWorkspacePerm } from "@/lib/me-adapter";
import { WorkspaceAuditLogPage } from "@/components/workspace-audit-log-page";

export const Route = createFileRoute("/_app/workspace/$workspaceId/audit-log")({
  beforeLoad: async ({ params }) => {
    const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
    if (!hasWorkspacePerm(me, params.workspaceId, "workspace.audit.read")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/audit-log",
  });
  return <WorkspaceAuditLogPage workspaceId={workspaceId} />;
}
