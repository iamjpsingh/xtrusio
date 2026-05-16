import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  deletePlatformInvite,
  errorCode,
  fetchPlatformInvites,
  postPlatformInvite,
  type PlatformInvite,
} from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/page-header";
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

function InviteDialog() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "editor">("admin");
  const [open, setOpen] = useState(false);
  const m = useMutation({
    mutationFn: () => postPlatformInvite(email, role),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["platform-invites"] });
      setOpen(false);
      setEmail("");
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Invite user</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a platform user</DialogTitle>
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
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as "admin" | "editor")}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="editor">Editor</SelectItem>
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

export function UsersPage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["platform-invites"],
    queryFn: fetchPlatformInvites,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => deletePlatformInvite(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-invites"] }),
  });
  const invites: PlatformInvite[] = data?.items ?? [];
  return (
    <div className="space-y-6">
      <PageHeader
        title="Platform users"
        description="Users with access to manage the platform itself."
        action={<InviteDialog />}
      />
      <section>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Pending invites</h2>
        {invites.length === 0 ? (
          <p className="text-sm text-muted-foreground">No pending invites.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {invites.map((i) => (
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
    </div>
  );
}
