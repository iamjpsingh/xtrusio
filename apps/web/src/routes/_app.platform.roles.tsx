import { createFileRoute } from "@tanstack/react-router";
import { PlatformRolesPage } from "@/components/platform-roles-page";

export const Route = createFileRoute("/_app/platform/roles")({
  component: PlatformRolesPage,
});
