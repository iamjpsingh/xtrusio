import { createFileRoute } from "@tanstack/react-router";
import { Shield } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/workspace/$workspaceId/roles")({
  component: RolesPage,
});

function RolesPage() {
  return (
    <>
      <PageHeader title="Roles" description="Custom workspace roles and their permission sets." />
      <EmptyState
        icon={Shield}
        title="Roles management ships in P6c"
        description="Backed by /api/workspaces/$wid/roles."
      />
    </>
  );
}
