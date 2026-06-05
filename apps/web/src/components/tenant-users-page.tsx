import { useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, MailX } from "lucide-react";
import { deleteTenantInvite, fetchTenantInvites, type TenantInvite } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { ScopedInviteDialog } from "@/components/scoped-invite-dialog";

export function TenantUsersPage() {
  const { slug } = useParams({ strict: false }) as { slug: string };
  const qc = useQueryClient();
  const { me, isLoading: meLoading } = useMe();
  const myTenant = me?.tenants.find((t) => t.slug === slug);
  const tenantId = myTenant?.id ?? "";
  const {
    data: invites,
    isPending: invitesPending,
    isError: invitesError,
    refetch: refetchInvites,
  } = useQuery({
    queryKey: qk.tenantInvites(tenantId),
    queryFn: () => fetchTenantInvites(tenantId),
    enabled: !!myTenant,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => deleteTenantInvite(tenantId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.tenantInvites(tenantId) }),
  });

  // The page resolves the tenant from the VIEWER's own memberships (`me.tenants`).
  // A platform admin who is not a member of this client workspace has no
  // membership row here — so today there is no workspace-scoped data we can show.
  // Render an explicit "limited view" state instead of a blank screen.
  // FOLLOW-UP: a platform-scoped endpoint (get tenant by slug + list its members,
  // gated by `platform.clients.read`) is needed to show full per-client info for
  // a non-member platform admin — that's a separate slice.
  if (!myTenant) {
    if (meLoading) {
      return (
        <div className="space-y-2 rounded-md border border-border bg-card p-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      );
    }
    return (
      <>
        <PageHeader title={`${slug} — Users`} description="Workspace membership for this client." />
        <EmptyState
          icon={Eye}
          title="Limited view"
          description="You're not a member of this workspace, so its members and invitations aren't shown here. Full per-client visibility for platform admins is coming soon."
        />
      </>
    );
  }
  const canInvite = hasWorkspacePerm(me, myTenant.id, "workspace.members.invite");
  // "owner" is the workspace governance role; only owner may pick the
  // "admin" invite role. This mirrors the workspace-members invite contract.
  const canPickAdmin = myTenant.role === "owner";
  return (
    <>
      <PageHeader
        title={`${myTenant.name} — Users`}
        description="Manage who has access to this workspace."
        action={
          canInvite ? (
            <ScopedInviteDialog
              targetId={myTenant.id}
              canPickAdmin={canPickAdmin}
              invalidateKey={qk.tenantInvites(myTenant.id)}
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
    </>
  );
}
