import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Cpu } from "lucide-react";
import type { JobRunOut } from "@xtrusio/api-types";
import { fetchPlatformJobRuns } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasPlatformPerm, useMe } from "@/lib/me-adapter";
import { formatDateTime } from "@/lib/format";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LoadMoreButton } from "@/components/audit/load-more-button";
import { JobRunDetailDrawer } from "@/components/system/job-run-detail-drawer";
import { formatDuration, jobStatusVariant } from "@/components/system/job-run-format";

export function PlatformSystemJobsPage() {
  // Deep-link fallback; the route beforeLoad is the primary gate. Reuses the
  // audit-read gate (same operator audience).
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.audit.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body />;
}

function Body() {
  const [selected, setSelected] = useState<JobRunOut | null>(null);

  const query = useInfiniteQuery({
    queryKey: qk.platformJobRuns(),
    queryFn: ({ pageParam }) => fetchPlatformJobRuns(pageParam ?? undefined),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const runs = useMemo<JobRunOut[]>(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const nextCursor = query.hasNextPage ? "more" : null;

  const header = (
    <PageHeader
      title="System jobs"
      description="Background-worker activity — what each job ran, when, how long it took, and its outcome. Click a row for detail."
    />
  );

  if (query.isPending) {
    return (
      <>
        {header}
        <TableSkeleton
          columns={6}
          columnWidths={["w-44", "w-40", "w-24", "w-24", "w-48", "w-24"]}
        />
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

  if (runs.length === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={Cpu}
          title="No job runs yet"
          description="Worker activity (invite emails, future scheduled jobs) will appear here once a job runs."
        />
      </>
    );
  }

  return (
    <>
      {header}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-44">Started</TableHead>
            <TableHead>Job</TableHead>
            <TableHead className="w-24">Status</TableHead>
            <TableHead className="w-24">Duration</TableHead>
            <TableHead className="w-48">Items (ok / failed)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((r) => (
            <TableRow key={r.id} className="cursor-pointer" onClick={() => setSelected(r)}>
              <TableCell className="text-xs text-muted-foreground">
                <time dateTime={r.started_at} title={new Date(r.started_at).toISOString()}>
                  {formatDateTime(r.started_at)}
                </time>
              </TableCell>
              <TableCell className="font-mono text-xs">{r.job_name}</TableCell>
              <TableCell>
                <Badge variant={jobStatusVariant(r.status)} className="capitalize">
                  {r.status}
                </Badge>
              </TableCell>
              <TableCell className="text-sm">{formatDuration(r.duration_ms)}</TableCell>
              <TableCell className="text-sm">
                {r.items_succeeded} ok
                {r.items_failed > 0 ? ` · ${r.items_failed} failed` : ""} / {r.items_processed}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <LoadMoreButton
        nextCursor={nextCursor}
        pending={query.isFetchingNextPage}
        onClick={() => void query.fetchNextPage()}
      />
      <JobRunDetailDrawer
        run={selected}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
      />
    </>
  );
}
