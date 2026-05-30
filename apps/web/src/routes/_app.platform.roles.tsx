import { createFileRoute, redirect } from "@tanstack/react-router";
import { fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { getDefaultLandingPath, hasPlatformPerm } from "@/lib/me-adapter";
import { PlatformRolesPage } from "@/components/platform-roles-page";

export const Route = createFileRoute("/_app/platform/roles")({
  // M10: route-level perm gate. Reuses the cached `me` (AuthGuard already
  // populated it); redirects before the component mounts on a deep-link.
  beforeLoad: async () => {
    const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
    if (!hasPlatformPerm(me, "platform.roles.manage")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: PlatformRolesPage,
});
