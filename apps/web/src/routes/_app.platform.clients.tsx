import { createFileRoute, redirect } from "@tanstack/react-router";
import { fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { getDefaultLandingPath, hasPlatformPerm } from "@/lib/me-adapter";
import { ClientsPage } from "@/components/clients-page";

export const Route = createFileRoute("/_app/platform/clients")({
  beforeLoad: async () => {
    const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
    if (!hasPlatformPerm(me, "platform.clients.read")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: ClientsPage,
});
