import { createFileRoute, redirect } from "@tanstack/react-router";
import { fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { getDefaultLandingPath, hasPlatformPerm } from "@/lib/me-adapter";
import { PlatformUsersPage } from "@/components/platform-users-page";

export const Route = createFileRoute("/_app/platform/users")({
  beforeLoad: async () => {
    const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
    if (!hasPlatformPerm(me, "platform.users.read")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: PlatformUsersPage,
});
