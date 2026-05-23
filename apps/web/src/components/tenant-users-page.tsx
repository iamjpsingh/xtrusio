import { useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  deleteTenantInvite,
  errorCode,
  fetchTenantInvites,
  postTenantInvite,
  type TenantInvite,
} from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { hasWorkspacePerm, useMe } from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageHeader } from "@/components/page-header";

type TenantRole = "admin" | "editor" | "read_only";

function InviteTenantDialog({
  tenantId,
  inviterRole,
}: {
  tenantId: string;
  inviterRole: "owner" | "admin";
}) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<TenantRole>(inviterRole === "owner" ? "admin" : "editor");
  const [open, setOpen] = useState(false);
  const allowed: TenantRole[] =
    inviterRole === "owner" ? ["admin", "editor", "read_only"] : ["editor", "read_only"];
  const m = useMutation({
    mutationFn: () => postTenantInvite(tenantId, email, role),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["tenant-invites", tenantId] });
      setOpen(false);
      setEmail("");
      setRole(inviterRole === "owner" ? "admin" : "editor");
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Invite user</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a user to this workspace</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate();
          }}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as TenantRole)}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {allowed.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {m.error ? (
            <p className="text-sm text-destructive">{errorMessage(errorCode(m.error))}</p>
          ) : null}
          <Button type="submit" disabled={m.isPending} className="w-full">
            {m.isPending ? "Sending…" : "Send invite"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function TenantUsersPage() {
  const { slug } = useParams({ strict: false }) as { slug: string };
  const qc = useQueryClient();
  const { me } = useMe();
  const myTenant = me?.tenants.find((t) => t.slug === slug);
  const tenantId = myTenant?.id ?? "";
  const { data: invites } = useQuery({
    queryKey: ["tenant-invites", tenantId],
    queryFn: () => fetchTenantInvites(tenantId),
    enabled: !!myTenant,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => deleteTenantInvite(tenantId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant-invites", tenantId] }),
  });
  if (!myTenant) return null;
  const canInvite = hasWorkspacePerm(me, myTenant.id, "workspace.members.invite");
  // "owner" is the workspace governance role; only owner may pick the
  // "admin" invite role. The legacy invite contract still scopes role-picker
  // options by inviter role, separate from the outer authorization gate.
  const inviterRole: "owner" | "admin" = myTenant.role === "owner" ? "owner" : "admin";
  return (
    <div className="space-y-6">
      <PageHeader
        title={`${myTenant.name} — Users`}
        description="Manage who has access to this workspace."
        action={
          canInvite ? <InviteTenantDialog tenantId={myTenant.id} inviterRole={inviterRole} /> : null
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
