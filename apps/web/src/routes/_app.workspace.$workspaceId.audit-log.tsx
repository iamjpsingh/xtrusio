import { createFileRoute } from "@tanstack/react-router";
import { ScrollText } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/audit-log")({
  component: AuditLogPage,
});

function AuditLogPage() {
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every RBAC mutation in this workspace, in reverse chronological order."
      />
      <EmptyState
        icon={ScrollText}
        title="Audit log ships in P6c"
        description="Backed by /api/workspaces/$wid/audit-log (cursor paginated)."
      />
    </>
  );
}
