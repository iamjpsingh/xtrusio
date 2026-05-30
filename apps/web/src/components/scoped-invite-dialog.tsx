// apps/web/src/components/scoped-invite-dialog.tsx
// Shared invite dialog (M11) used by both the platform-clients tenant-users
// view and the workspace-members view. The only differences between the two
// originals were the invalidation key and how "may pick admin" is derived, so
// both are passed in by the caller.

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { QueryKey } from "@tanstack/react-query";
import { errorCode, postTenantInvite } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
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

type InviteRole = "admin" | "editor" | "read_only";

type Props = {
  /** Tenant/workspace id the invite is scoped to. */
  targetId: string;
  /** Whether the inviter may pick the "admin" role (owner-only). */
  canPickAdmin: boolean;
  /** Invites-list query key to invalidate on success. */
  invalidateKey: QueryKey;
};

export function ScopedInviteDialog({ targetId, canPickAdmin, invalidateKey }: Props) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>(canPickAdmin ? "admin" : "editor");
  const [open, setOpen] = useState(false);
  const allowed: InviteRole[] = canPickAdmin
    ? ["admin", "editor", "read_only"]
    : ["editor", "read_only"];
  const m = useMutation({
    mutationFn: () => postTenantInvite(targetId, email, role),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: invalidateKey });
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
