import { useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailX, Users } from "lucide-react";
import {
  deleteTenantInvite,
  fetchPlatformClient,
  fetchTenantInvites,
  type TenantInvite,
} from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { ScopedInviteDialog } from "@/components/scoped-invite-dialog";

// The per-client detail page is reached via the platform route
// (gated on `platform.clients.read`). Client info + members now come from the
// platform-scope endpoint (`GET /api/platform/clients/{slug}`) so a platform
// operator who provisioned but never JOINED the tenant still sees its name and
// members — no more "limited view" dead-end.
//
// The invites section is workspace-scoped (it reads/writes the tenant's invites
// and requires workspace membership), so it only renders when the viewer is a
// member of this tenant (i.e. the slug is in `me.tenants`).
export function TenantUsersPage() {
  const { slug } = useParams({ strict: false }) as { slug: string };
  const qc = useQueryClient();
  const { me } = useMe();
  const myTenant = me?.tenants.find((t) => t.slug === slug);

  const client = useQuery({
    queryKey: qk.platformClient(slug),
    queryFn: () => fetchPlatformClient(slug),
  });

  // Invites are only meaningful for a viewer who is a member of the tenant.
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

  const canInvite = !!myTenant && hasWorkspacePerm(me, myTenant.id, "workspace.members.invite");
  // "owner" is the workspace governance role; only owner may pick the
  // "admin" invite role. This mirrors the workspace-members invite contract.
  const canPickAdmin = myTenant?.role === "owner";

  const title = client.data ? `${client.data.name} — Users` : `${slug} — Users`;

  let membersBody: React.ReactNode;
  if (client.isPending) {
    membersBody = <TableSkeleton columns={3} columnWidths={["w-56", "w-32", "w-48"]} />;
  } else if (client.isError) {
    membersBody = <ErrorState onRetry={() => void client.refetch()} />;
  } else if (client.data.members.length === 0) {
    membersBody = (
      <EmptyState
        icon={Users}
        title="No members yet"
        description="Invite a teammate to this workspace and they'll appear here once they join."
      />
    );
  } else {
    membersBody = (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead className="w-32">Role</TableHead>
            <TableHead className="w-48">Joined</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {client.data.members.map((m) => (
            <TableRow key={m.auth_user_id}>
              <TableCell>
                <span className="font-medium">{m.email ?? "—"}</span>
              </TableCell>
              <TableCell>
                <Badge variant="outline" className="font-mono">
                  {m.role}
                </Badge>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                <time dateTime={m.joined_at} title={m.joined_at}>
                  {formatDateTime(m.joined_at)}
                </time>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }

  return (
    <>
      <PageHeader
        title={title}
        description="Members and invitations for this client workspace."
        action={
          canInvite && myTenant ? (
            <ScopedInviteDialog
              targetId={myTenant.id}
              canPickAdmin={canPickAdmin}
              invalidateKey={qk.tenantInvites(myTenant.id)}
            />
          ) : null
        }
      />

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">Members</h2>
        {membersBody}
      </section>

      {myTenant ? (
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">Invitations</h2>
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
      ) : null}
    </>
  );
}
