// apps/web/src/components/platform-users-page.tsx
// Platform-scope users administration. Lists every user with platform
// access, their legacy role enum, their granted custom-role count, and
// their last-sign-in time. The [Manage roles] button per row opens the
// shared <GrantManagerDialog> Sheet to grant/revoke specific platform
// roles. Gated by `platform.users.read`; `[Manage roles]` itself is
// gated by `platform.users.manage` (defense-in-depth — the backend
// also gates the POST/DELETE endpoints).

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Users } from "lucide-react";
import type { PlatformUserListItem } from "@xtrusio/api-types";
import { fetchPlatformUsers } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasPlatformPerm, isSuperAdmin, useMe } from "@/lib/me-adapter";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { LoadMoreButton } from "@/components/audit/load-more-button";
import { GrantManagerDialog } from "@/components/grants/grant-manager-dialog";
import { PlatformProvisionDialog } from "@/components/platform-provision-dialog";

export function PlatformUsersPage() {
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.users.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  const canManage = hasPlatformPerm(me, "platform.users.manage");
  // ROLE gate (not permission): a platform admin holds `platform.users.manage`
  // but only a super_admin may mint new platform users.
  const canProvision = isSuperAdmin(me);
  return <Body canManage={canManage} canProvision={canProvision} />;
}

function Body({ canManage, canProvision }: { canManage: boolean; canProvision: boolean }) {
  const [selected, setSelected] = useState<PlatformUserListItem | null>(null);

  // H3: useInfiniteQuery owns the page accumulator (no setState in queryFn).
  const query = useInfiniteQuery({
    queryKey: qk.platformUsers(),
    queryFn: ({ pageParam }) => fetchPlatformUsers(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const users = useMemo<PlatformUserListItem[]>(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const nextCursor = query.hasNextPage ? "more" : null;

  const header = (
    <PageHeader
      title="Platform users"
      description="People with access to the platform. Use Manage roles to grant or revoke platform-scope custom roles."
      action={canProvision ? <PlatformProvisionDialog /> : null}
    />
  );

  // First-load skeleton: no accumulated pages yet and a fetch is in flight.
  if (query.isPending) {
    return (
      <>
        {header}
        <TableSkeleton columns={5} columnWidths={["w-56", "w-20", "w-12", "w-40", "w-24"]} />
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

  if (users.length === 0) {
    return (
      <>
        {header}
        <EmptyState
          icon={Users}
          title="No platform users yet"
          description="People you grant platform access to will appear here."
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
            <TableHead>Email</TableHead>
            <TableHead className="w-32">Role</TableHead>
            <TableHead className="w-24">Grants</TableHead>
            <TableHead className="w-48">Last sign in</TableHead>
            <TableHead className="w-32" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => (
            <TableRow key={u.id}>
              <TableCell>
                <span className="font-medium">{u.email}</span>
                {!u.is_active ? (
                  <Badge variant="secondary" className="ml-2">
                    Inactive
                  </Badge>
                ) : null}
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="font-mono">
                  {u.role}
                </Badge>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {u.granted_role_count}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                <time
                  dateTime={u.last_sign_in_at ?? undefined}
                  title={u.last_sign_in_at ?? "Never"}
                >
                  {formatDateTime(u.last_sign_in_at, { fallback: "Never" })}
                </time>
              </TableCell>
              <TableCell className="text-right">
                {canManage ? (
                  <Button variant="outline" size="sm" onClick={() => setSelected(u)}>
                    Manage roles
                  </Button>
                ) : null}
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
      {selected ? (
        <GrantManagerDialog
          scope="platform"
          open
          userId={selected.id}
          email={selected.email}
          onOpenChange={(o) => {
            if (!o) setSelected(null);
          }}
        />
      ) : null}
    </>
  );
}
