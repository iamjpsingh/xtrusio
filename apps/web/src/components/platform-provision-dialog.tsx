// apps/web/src/components/platform-provision-dialog.tsx
// super_admin-only platform-user provisioning. A single dialog with two paths
// behind a segmented Tabs toggle:
//   - Create directly — email + password + role(admin) -> POST /api/platform/users
//   - Invite          — email + role(admin)            -> POST /api/platform/users/invites
// Both endpoints are super_admin-gated on the backend; the affordance that
// renders this dialog is gated by `isSuperAdmin(me)` at the call site, so this
// component assumes the caller already cleared that bar.
//
// A platform `admin` holds `platform.users.manage` (and may grant/revoke roles
// via the per-row Manage roles dialog) but must NOT be able to mint users —
// hence the role gate, not a permission gate, on the entry point.

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorCode, postPlatformInvite, postPlatformUser } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

const MIN_PASSWORD_LENGTH = 8;

export function PlatformProvisionDialog() {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Add platform user</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a platform user</DialogTitle>
          <DialogDescription>
            Create the account directly with a password, or send an email invite.
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="create" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="create">Create directly</TabsTrigger>
            <TabsTrigger value="invite">Invite</TabsTrigger>
          </TabsList>
          <TabsContent value="create">
            <CreateForm onDone={() => setOpen(false)} />
          </TabsContent>
          <TabsContent value="invite">
            <InviteForm onDone={() => setOpen(false)} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function CreateForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const m = useMutation({
    mutationFn: () => postPlatformUser({ email, password, role: "admin" }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformUsers() });
      setEmail("");
      setPassword("");
      toast.success("Platform user created");
      onDone();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
      className="space-y-4 pt-4"
    >
      <div className="space-y-1.5">
        <Label htmlFor="create-email">Email</Label>
        <Input
          id="create-email"
          type="email"
          required
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={m.isPending}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="create-password">Password</Label>
        <Input
          id="create-password"
          type="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={m.isPending}
        />
        <p className="text-xs text-muted-foreground">At least {MIN_PASSWORD_LENGTH} characters.</p>
      </div>
      {m.error ? (
        <p className="text-sm text-destructive">{errorMessage(errorCode(m.error))}</p>
      ) : null}
      <Button type="submit" disabled={m.isPending} className="w-full">
        {m.isPending ? "Creating…" : "Create platform user"}
      </Button>
    </form>
  );
}

function InviteForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");

  const m = useMutation({
    mutationFn: () => postPlatformInvite(email, "admin"),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformUsers() });
      setEmail("");
      toast.success("Invite sent");
      onDone();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
      className="space-y-4 pt-4"
    >
      <div className="space-y-1.5">
        <Label htmlFor="invite-email">Email</Label>
        <Input
          id="invite-email"
          type="email"
          required
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={m.isPending}
        />
      </div>
      {m.error ? (
        <p className="text-sm text-destructive">{errorMessage(errorCode(m.error))}</p>
      ) : null}
      <Button type="submit" disabled={m.isPending} className="w-full">
        {m.isPending ? "Sending…" : "Send invite"}
      </Button>
    </form>
  );
}
