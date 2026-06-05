// apps/web/src/components/clients-page.tsx
// Platform "Clients" view. Lists every client tenant onboarded to the platform
// and links each row to its per-client users view. `GET /api/tenants` returns
// the cursor-paginated `TenantsPage` envelope (`items` + `next_cursor`) — this
// page reads `items` and drives [Load more] off `next_cursor`, mirroring the
// platform-users page. Gated by `platform.clients.read` (enforced in the
// route's `beforeLoad`; the backend is the primary gate).

import { Link } from "@tanstack/react-router";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Building2 } from "lucide-react";
import type { TenantOut } from "@xtrusio/api-types";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { fetchTenants } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { CreateClientDialog } from "@/components/create-client-dialog";
import { LoadMoreButton } from "@/components/audit/load-more-button";

export function ClientsPage() {
  const query = useInfiniteQuery({
    queryKey: qk.tenants(),
    queryFn: ({ pageParam }) => fetchTenants(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const tenants = useMemo<TenantOut[]>(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const nextCursor = query.hasNextPage ? "more" : null;

  const action = <CreateClientDialog trigger={<Button>Create client</Button>} />;
  const header = (
    <PageHeader
      title="Client tenants"
      description="Companies onboarded to the platform."
      action={action}
    />
  );

  if (query.isPending) {
    return (
      <>
        {header}
        <TableSkeleton columns={3} columnWidths={["w-40", "w-28", "w-24"]} />
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

  if (tenants.length === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={Building2}
          title="No client tenants yet"
          description="Create your first one with the button above."
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
            <TableHead>Name</TableHead>
            <TableHead>Slug</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tenants.map((t) => (
            <TableRow key={t.id}>
              <TableCell className="font-medium">
                <Link
                  to="/platform/clients/$slug/users"
                  params={{ slug: t.slug }}
                  className="text-foreground hover:underline"
                >
                  {t.name}
                </Link>
              </TableCell>
              <TableCell className="text-muted-foreground font-mono">{t.slug}</TableCell>
              <TableCell className="text-muted-foreground tabular-nums">
                {new Date(t.created_at).toLocaleDateString()}
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
    </>
  );
}
