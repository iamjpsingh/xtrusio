import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ScrollText } from "lucide-react";
import type { AuditEventOut } from "@xtrusio/api-types";
import { fetchPlatformAuditLog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasPlatformPerm, useMe } from "@/lib/me-adapter";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditDetailDrawer } from "@/components/audit/audit-detail-drawer";
import { AuditCategoryFilter } from "@/components/audit/audit-category-filter";
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
  // The category filter is part of the query key, so switching it transparently
  // resets the useInfiniteQuery accumulator (re-fetches from cursor=null).
  const [category, setCategory] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditEventOut | null>(null);

  // H3: useInfiniteQuery owns the page accumulator — no useState mutated inside
  // queryFn. TanStack keeps pages cached across nav, so the user resumes where
  // they left off instead of re-fetching from cursor=null.
  const query = useInfiniteQuery({
    queryKey: qk.platformAudit(category),
    queryFn: ({ pageParam }) => fetchPlatformAuditLog(pageParam ?? undefined, category),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const events = useMemo<AuditEventOut[]>(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const nextCursor = query.hasNextPage ? "more" : null;

  const toolbar = (
    <>
      <PageHeader
        title="Platform audit log"
        description="Every platform-scope action in reverse-chronological order. Click a row to inspect the before/after detail."
      />
      <div className="mb-4 flex items-center justify-end">
        <AuditCategoryFilter value={category} onChange={setCategory} />
      </div>
    </>
  );

  function content() {
    if (query.isPending) {
      return (
        <TableSkeleton
          columns={6}
          columnWidths={["w-40", "w-48", "w-40", "w-28", "w-20", "w-40"]}
        />
      );
    }
    if (query.isError) {
      return <ErrorState onRetry={() => void query.refetch()} />;
    }
    if (events.length === 0) {
      return (
        <EmptyState
          icon={ScrollText}
          title="No activity yet"
          description={
            category
              ? "No activity in this category yet. Try a different filter."
              : "Platform-scope actions will appear here as they happen."
          }
        />
      );
    }
    return (
      <>
        <AuditTable events={events} onSelect={setSelected} />
        <LoadMoreButton
          nextCursor={nextCursor}
          pending={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
        />
      </>
    );
  }

  return (
    <>
      {toolbar}
      {content()}
      <AuditDetailDrawer
        event={selected}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
      />
    </>
  );
}
