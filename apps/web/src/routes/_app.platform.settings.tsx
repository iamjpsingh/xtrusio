import { createFileRoute, redirect } from "@tanstack/react-router";
import { fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { getDefaultLandingPath, hasPlatformPerm } from "@/lib/me-adapter";
import { SettingsPage } from "@/components/settings-page";

export const Route = createFileRoute("/_app/platform/settings")({
  beforeLoad: async () => {
    const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
    if (!hasPlatformPerm(me, "platform.settings.read")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: SettingsPage,
});
