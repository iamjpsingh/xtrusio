import { useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteTenantInvite, fetchTenantInvites, type TenantInvite } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { ScopedInviteDialog } from "@/components/scoped-invite-dialog";

export function TenantUsersPage() {
  const { slug } = useParams({ strict: false }) as { slug: string };
  const qc = useQueryClient();
  const { me } = useMe();
  const myTenant = me?.tenants.find((t) => t.slug === slug);
  const tenantId = myTenant?.id ?? "";
  const { data: invites } = useQuery({
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
    <div className="space-y-6">
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
        {invites && invites.items.length > 0 ? (
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
        ) : (
          <p className="text-sm text-muted-foreground">No invitations yet.</p>
        )}
      </section>
    </div>
  );
}
