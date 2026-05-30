import { createFileRoute, redirect } from "@tanstack/react-router";
import { fetchMe } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { getDefaultLandingPath, hasPlatformPerm } from "@/lib/me-adapter";
import { PlatformAuditLogPage } from "@/components/platform-audit-log-page";

export const Route = createFileRoute("/_app/platform/audit-log")({
  beforeLoad: async () => {
    const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
    if (!hasPlatformPerm(me, "platform.audit.read")) {
      throw redirect({ to: getDefaultLandingPath(me) });
    }
  },
  component: PlatformAuditLogPage,
});
