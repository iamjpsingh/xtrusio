import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { MeResponse } from "@xtrusio/api-types";
import type { TenantInvite } from "@/lib/api";
import { deleteTenantInvite, fetchTenantInvites } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { findTenant, getDefaultLandingPath, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { MailX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { ScopedInviteDialog } from "@/components/scoped-invite-dialog";
import { WorkspaceMembersListPage } from "@/components/workspace-members-list-page";

export function WorkspaceMembersPage({ workspaceId }: { workspaceId: string }) {
  // Deep-link fallback; the route's beforeLoad gate is the primary guard.
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.members.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body me={me} workspaceId={workspaceId} />;
}

function Body({ me, workspaceId }: { me: MeResponse | null; workspaceId: string }) {
  const qc = useQueryClient();
  const tenant = findTenant(me, workspaceId);
  const canInvite = hasWorkspacePerm(me, workspaceId, "workspace.members.invite");
  // "owner" is the workspace governance role; only owner may invite an admin.
  // This mirrors the legacy invite contract used by tenant-users-page.
  const canPickAdmin = tenant?.role === "owner";

  const {
    data: invites,
    isPending: invitesPending,
    isError: invitesError,
    refetch: refetchInvites,
  } = useQuery({
    queryKey: qk.workspaceInvites(workspaceId),
    queryFn: () => fetchTenantInvites(workspaceId),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => deleteTenantInvite(workspaceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.workspaceInvites(workspaceId) }),
  });

  return (
    <>
      <PageHeader
        title={`${tenant?.name ?? "Workspace"} — Members`}
        description="People with access to this workspace. Invite new members, list pending invites, and manage existing members' roles."
        action={
          canInvite ? (
            <ScopedInviteDialog
              targetId={workspaceId}
              canPickAdmin={canPickAdmin}
              invalidateKey={qk.workspaceInvites(workspaceId)}
            />
          ) : null
        }
      />
      <section>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Invitations</h2>
        {invitesPending ? (
          <div className="space-y-2 rounded-md border border-border bg-card p-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : invitesError ? (
          <ErrorState onRetry={() => void refetchInvites()} />
        ) : invites.items.length === 0 ? (
          <EmptyState
            icon={MailX}
            title="No invitations yet"
            description="Invite a teammate to this workspace and pending invites will show up here."
          />
        ) : (
          <ul className="divide-y rounded-md border">
            {invites.items.map((i: TenantInvite) => (
              <li key={i.id} className="flex items-center justify-between p-4">
                <div>
                  <p className="font-medium">{i.email}</p>
                  <p className="text-xs text-muted-foreground">{i.role}</p>
                </div>
                {i.accepted_at ? (
                  <span className="text-xs text-foreground">Accepted</span>
                ) : i.revoked_at ? (
                  <span className="text-xs text-muted-foreground">Revoked</span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => revoke.mutate(i.id)}
                    disabled={revoke.isPending}
                  >
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <Separator />
      <WorkspaceMembersListPage workspaceId={workspaceId} />
    </>
  );
}
