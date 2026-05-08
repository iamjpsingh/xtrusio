import { createFileRoute } from "@tanstack/react-router";
import { Building2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/clients")({
  component: ClientsRoute,
});

function ClientsRoute() {
  return (
    <>
      <PageHeader title="Client tenants" description="Companies onboarded to the platform." />
      <EmptyState
        icon={Building2}
        title="No client tenants yet"
        description="The first tenant is created here once the tenancy and auth plans land (1B and 1C)."
        action={{
          label: "Create a client",
          onClick: () => {},
          disabled: true,
          reason: "Available in Plan 1E (user management)",
        }}
      />
    </>
  );
}
