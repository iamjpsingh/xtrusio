import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { AuditEventOut } from "@xtrusio/api-types";
import { fetchPlatformAuditLog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasPlatformPerm, useMe } from "@/lib/me-adapter";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditDetailDrawer } from "@/components/audit/audit-detail-drawer";
import { LoadMoreButton } from "@/components/audit/load-more-button";

export function PlatformAuditLogPage() {
  // Defense-in-depth deep-link fallback: the route's beforeLoad gate is the
  // primary guard, but this keeps a direct component mount from leaking data.
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.audit.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body />;
}

function Body() {
  // H3: useInfiniteQuery owns the page accumulator — no useState mutated inside
  // queryFn. TanStack keeps pages cached across nav, so the user resumes where
  // they left off instead of re-fetching from cursor=null.
  const query = useInfiniteQuery({
    queryKey: qk.platformAudit(),
    queryFn: ({ pageParam }) => fetchPlatformAuditLog(pageParam ?? undefined),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const events = useMemo<AuditEventOut[]>(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const nextCursor = query.hasNextPage ? "more" : null;

  const [selected, setSelected] = useState<AuditEventOut | null>(null);

  return (
    <>
      <PageHeader
        title="Platform audit log"
        description="Every platform-scope RBAC mutation in reverse-chronological order. Click a row to inspect before/after JSON."
      />
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
