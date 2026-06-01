import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ScrollText } from "lucide-react";
import type { AuditEventOut } from "@xtrusio/api-types";
import { fetchWorkspaceAuditLog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditDetailDrawer } from "@/components/audit/audit-detail-drawer";
import { LoadMoreButton } from "@/components/audit/load-more-button";

export function WorkspaceAuditLogPage({ workspaceId }: { workspaceId: string }) {
  // Deep-link fallback; the route beforeLoad is the primary gate.
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.audit.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body workspaceId={workspaceId} />;
}

function Body({ workspaceId }: { workspaceId: string }) {
  // H3: useInfiniteQuery owns the accumulator (no setState inside queryFn).
  const query = useInfiniteQuery({
    queryKey: qk.workspaceAudit(workspaceId),
    queryFn: ({ pageParam }) => fetchWorkspaceAuditLog(workspaceId, pageParam ?? undefined),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const events = useMemo<AuditEventOut[]>(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const nextCursor = query.hasNextPage ? "more" : null;

  const [selected, setSelected] = useState<AuditEventOut | null>(null);

  const header = (
    <PageHeader
      title="Workspace audit log"
      description="Every RBAC mutation in this workspace, reverse-chronological."
    />
  );

  if (query.isPending) {
    return (
      <>
        {header}
        <TableSkeleton columns={4} columnWidths={["w-40", "w-52", "w-32", "w-44"]} />
      </>
    );
  }

  if (query.isError) {
    return (
      <>
        {header}
        <ErrorState onRetry={() => void query.refetch()} />
      </>
    );
  }

  if (events.length === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={ScrollText}
          title="No activity yet"
          description="RBAC changes in this workspace will appear here as they happen."
        />
      </>
    );
  }

  return (
    <>
      {header}
      <AuditTable events={events} onSelect={setSelected} />
      <LoadMoreButton
        nextCursor={nextCursor}
        pending={query.isFetchingNextPage}
        onClick={() => void query.fetchNextPage()}
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
