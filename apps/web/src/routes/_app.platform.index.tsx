import { createFileRoute } from "@tanstack/react-router";
import { PlatformDashboardPage } from "@/components/platform-dashboard-page";

export const Route = createFileRoute("/_app/platform/")({
  component: PlatformDashboardPage,
});
