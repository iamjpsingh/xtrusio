import { createFileRoute } from "@tanstack/react-router";
import { PlatformUsersPage } from "@/components/platform-users-page";

export const Route = createFileRoute("/_app/platform/users")({
  component: PlatformUsersPage,
});
