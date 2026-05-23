import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Info } from "lucide-react";
import type { MeResponse } from "@xtrusio/api-types";
import type { TenantInvite } from "@/lib/api";
import { deleteTenantInvite, errorCode, fetchTenantInvites, postTenantInvite } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import { findTenant, getDefaultLandingPath, hasWorkspacePerm, useMe } from "@/lib/me-adapter";
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
import { Forbidden } from "@/components/forbidden";

type InviteRole = "admin" | "editor" | "read_only";

function InviteDialog({
  workspaceId,
  canPickAdmin,
}: {
  workspaceId: string;
  canPickAdmin: boolean;
}) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>(canPickAdmin ? "admin" : "editor");
  const [open, setOpen] = useState(false);
  const allowed: InviteRole[] = canPickAdmin
    ? ["admin", "editor", "read_only"]
    : ["editor", "read_only"];
  const m = useMutation({
    mutationFn: () => postTenantInvite(workspaceId, email, role),
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: qk.workspaceInvites(workspaceId),
      });
      setOpen(false);
      setEmail("");
      setRole(canPickAdmin ? "admin" : "editor");
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
            <Select value={role} onValueChange={(v) => setRole(v as InviteRole)}>
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

export function WorkspaceMembersPage({ workspaceId }: { workspaceId: string }) {
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

  const { data: invites } = useQuery({
    queryKey: qk.workspaceInvites(workspaceId),
    queryFn: () => fetchTenantInvites(workspaceId),
  });

  const revoke = useMutation({
    mutationFn: (id: string) => deleteTenantInvite(workspaceId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.workspaceInvites(workspaceId) }),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${tenant?.name ?? "Workspace"} — Members`}
        description="People with access to this workspace. Invite, list pending invites, and revoke them."
        action={
          canInvite ? <InviteDialog workspaceId={workspaceId} canPickAdmin={canPickAdmin} /> : null
        }
      />
      <section className="rounded-md border bg-muted/30 p-4 text-sm">
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-4 w-4 text-muted-foreground" aria-hidden />
          <p className="text-muted-foreground">
            Member listing ships in P6d. For now you can invite people and revoke pending invites;
            the full member list will appear here once the backend{" "}
            <code>GET /api/workspaces/{`{wid}`}/members</code> endpoint lands.
          </p>
        </div>
      </section>
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
