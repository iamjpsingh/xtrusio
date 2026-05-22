import { createFileRoute } from "@tanstack/react-router";
import { LayoutDashboard } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";

export const Route = createFileRoute("/_app/platform/")({
  component: DashboardRoute,
});

function DashboardRoute() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Platform-wide activity will appear here once the bootstrap and auth plans land."
      />
      <EmptyState
        icon={LayoutDashboard}
        title="Welcome to Xtrusio"
        description="The first platform owner is created via `make create-platform-owner`. Once signed in, this page shows platform-wide activity, recent runs, and tenant health."
      />
    </>
  );
}
