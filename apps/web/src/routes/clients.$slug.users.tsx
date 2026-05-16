import { createFileRoute } from "@tanstack/react-router";
import { TenantUsersPage } from "@/components/tenant-users-page";

export const Route = createFileRoute("/clients/$slug/users")({
  component: TenantUsersPage,
});
