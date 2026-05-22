import { createFileRoute } from "@tanstack/react-router";
import { PlatformAuditLogPage } from "@/components/platform-audit-log-page";

export const Route = createFileRoute("/_app/platform/audit-log")({
  component: PlatformAuditLogPage,
});
