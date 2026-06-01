import { createFileRoute } from "@tanstack/react-router";
import { Activity, Building2, LayoutDashboard, Users } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { StatCard } from "@/components/stat-card";

export const Route = createFileRoute("/_app/platform/")({
  component: DashboardRoute,
});

function DashboardRoute() {
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="A platform-wide overview. Live metrics arrive once activity flows through the system."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard icon={Building2} label="Client tenants" />
        <StatCard icon={Users} label="Platform users" />
        <StatCard icon={Activity} label="Recent activity" />
      </div>
      <EmptyState
        icon={LayoutDashboard}
        title="Nothing to report yet"
        description="As clients onboard and teams start working, platform activity, recent runs, and tenant health will surface here."
      />
    </>
  );
}
