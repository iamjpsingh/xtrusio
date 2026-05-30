// apps/web/src/components/workspace-members-list-page.tsx
// Lists every member of a workspace with their tenant role, granted
// custom-role count, and join date. [Manage roles] opens the shared
// <GrantManagerDialog scope="workspace" ...> Sheet. Embedded inside
// <WorkspaceMembersPage> below the invite section so both halves
// share the /workspace/$wid/members route.
//
// View gate: workspace.members.read.
// Manage-roles gate: workspace.members.manage.

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { WorkspaceMemberListItem } from "@xtrusio/api-types";
import { fetchWorkspaceMembers } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { getDefaultLandingPath, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
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
import { Forbidden } from "@/components/forbidden";
import { LoadMoreButton } from "@/components/audit/load-more-button";
import { GrantManagerDialog } from "@/components/grants/grant-manager-dialog";

export function WorkspaceMembersListPage({ workspaceId }: { workspaceId: string }) {
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.members.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  const canManage = hasWorkspacePerm(me, workspaceId, "workspace.members.manage");
  return <Body workspaceId={workspaceId} canManage={canManage} />;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

function Body({ workspaceId, canManage }: { workspaceId: string; canManage: boolean }) {
  const [selected, setSelected] = useState<WorkspaceMemberListItem | null>(null);

  // H3: useInfiniteQuery owns the page accumulator (no setState in queryFn).
  const query = useInfiniteQuery({
    queryKey: qk.workspaceMembers(workspaceId),
    queryFn: ({ pageParam }) => fetchWorkspaceMembers(workspaceId, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });

  const members = useMemo<WorkspaceMemberListItem[]>(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data],
  );
  const nextCursor = query.hasNextPage ? "more" : null;

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium text-muted-foreground">Members</h2>
      {members.length === 0 && !query.isFetching ? (
        <p className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          No members yet.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead className="w-32">Role</TableHead>
              <TableHead className="w-24">Grants</TableHead>
              <TableHead className="w-48">Joined</TableHead>
              <TableHead className="w-32" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {members.map((m) => (
              <TableRow key={m.user_id}>
                <TableCell>
                  <span className="font-medium">{m.email ?? "—"}</span>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className="font-mono">
                    {m.role}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {m.granted_role_count}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  <time dateTime={m.joined_at}>{formatDate(m.joined_at)}</time>
                </TableCell>
                <TableCell className="text-right">
                  {canManage ? (
                    <Button variant="outline" size="sm" onClick={() => setSelected(m)}>
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
        nextCursor={nextCursor}
        pending={query.isFetchingNextPage}
        onClick={() => void query.fetchNextPage()}
      />
      {selected ? (
        <GrantManagerDialog
          scope="workspace"
          open
          workspaceId={workspaceId}
          userId={selected.user_id}
          email={selected.email ?? "(deleted user)"}
          onOpenChange={(o) => {
            if (!o) setSelected(null);
          }}
        />
      ) : null}
    </section>
  );
}
