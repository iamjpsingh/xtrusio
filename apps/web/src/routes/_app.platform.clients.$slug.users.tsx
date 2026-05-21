import { createFileRoute } from "@tanstack/react-router";
import { TenantUsersPage } from "@/components/tenant-users-page";

export const Route = createFileRoute("/_app/platform/clients/$slug/users")({
  component: TenantUsersPage,
});
