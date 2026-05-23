// apps/web/src/components/platform-users-page.tsx
// Platform-scope users administration. Lists every user with platform
// access, their legacy role enum, their granted custom-role count, and
// their last-sign-in time. The [Manage roles] button per row opens the
// shared <GrantManagerDialog> Sheet to grant/revoke specific platform
// roles. Gated by `platform.users.read`; `[Manage roles]` itself is
// gated by `platform.users.manage` (defense-in-depth — the backend
// also gates the POST/DELETE endpoints).

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type {
  PlatformUserListItem,
  PlatformUsersPage as PlatformUsersPageType,
} from "@xtrusio/api-types";
import { fetchPlatformUsers } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasPlatformPerm, useMe } from "@/lib/me-adapter";
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
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { LoadMoreButton } from "@/components/audit/load-more-button";
import { GrantManagerDialog } from "@/components/grants/grant-manager-dialog";

export function PlatformUsersPage() {
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.users.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  const canManage = hasPlatformPerm(me, "platform.users.manage");
  return <Body canManage={canManage} />;
}

function formatTime(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

function Body({ canManage }: { canManage: boolean }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [pages, setPages] = useState<PlatformUsersPageType[]>([]);
  const [selected, setSelected] = useState<PlatformUserListItem | null>(null);

  const query = useQuery({
    queryKey: qk.platformUsersWithCursor(cursor),
    queryFn: async () => {
      const page = await fetchPlatformUsers(cursor);
      setPages((prev) => (cursor === null ? [page] : [...prev, page]));
      return page;
    },
  });

  const users = useMemo<PlatformUserListItem[]>(() => pages.flatMap((p) => p.items), [pages]);
  const lastPage = pages.length > 0 ? pages[pages.length - 1] : undefined;
  const lastCursor = lastPage ? lastPage.next_cursor : null;

  return (
    <>
      <PageHeader
        title="Platform users"
        description="People with access to the platform. Use Manage roles to grant or revoke platform-scope custom roles."
      />
      {users.length === 0 && !query.isFetching ? (
        <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No platform users yet.
        </p>
      ) : (
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
                    {formatTime(u.last_sign_in_at)}
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
      )}
      <LoadMoreButton
        nextCursor={lastCursor}
        pending={query.isFetching}
        onClick={() => setCursor(lastCursor)}
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
