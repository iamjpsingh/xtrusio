import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { AuditEventOut, AuditEventsPage } from "@xtrusio/api-types";
import { fetchWorkspaceAuditLog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import {
  getDefaultLandingPath,
  hasWorkspacePerm,
  useMe,
} from "@/lib/me-adapter";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditDetailDrawer } from "@/components/audit/audit-detail-drawer";
import { LoadMoreButton } from "@/components/audit/load-more-button";

export function WorkspaceAuditLogPage({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.audit.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body workspaceId={workspaceId} />;
}

function Body({ workspaceId }: { workspaceId: string }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [pages, setPages] = useState<AuditEventsPage[]>([]);

  const query = useQuery({
    queryKey: [...qk.workspaceAudit(workspaceId), cursor ?? "head"],
    queryFn: async () => {
      const page = await fetchWorkspaceAuditLog(
        workspaceId,
        cursor ?? undefined,
      );
      setPages((prev) => (cursor === null ? [page] : [...prev, page]));
      return page;
    },
  });

  const events = useMemo<AuditEventOut[]>(
    () => pages.flatMap((p) => p.items),
    [pages],
  );
  const lastPage = pages.length > 0 ? pages[pages.length - 1] : undefined;
  const lastCursor = lastPage ? lastPage.next_cursor : null;

  const [selected, setSelected] = useState<AuditEventOut | null>(null);

  return (
    <>
      <PageHeader
        title="Workspace audit log"
        description="Every RBAC mutation in this workspace, reverse-chronological."
      />
      <AuditTable events={events} onSelect={setSelected} />
      <LoadMoreButton
        nextCursor={lastCursor}
        pending={query.isFetching}
        onClick={() => setCursor(lastCursor)}
      />
      <AuditDetailDrawer
        event={selected}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
      />
    </>
  );
}
