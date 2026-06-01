import { useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailX } from "lucide-react";
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
  const { me } = useMe();
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
  if (!myTenant) return null;
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
