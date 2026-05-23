import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { AuditEventOut, AuditEventsPage } from "@xtrusio/api-types";
import { fetchPlatformAuditLog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import {
  getDefaultLandingPath,
  hasPlatformPerm,
  useMe,
} from "@/lib/me-adapter";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditDetailDrawer } from "@/components/audit/audit-detail-drawer";
import { LoadMoreButton } from "@/components/audit/load-more-button";

export function PlatformAuditLogPage() {
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.audit.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body />;
}

function Body() {
  // Local accumulator: each click on Load more appends a page.
  const [cursor, setCursor] = useState<string | null>(null);
  const [pages, setPages] = useState<AuditEventsPage[]>([]);

  const query = useQuery({
    queryKey: [...qk.platformAudit(), cursor ?? "head"],
    queryFn: async () => {
      const page = await fetchPlatformAuditLog(cursor ?? undefined);
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
        title="Platform audit log"
        description="Every platform-scope RBAC mutation in reverse-chronological order. Click a row to inspect before/after JSON."
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
