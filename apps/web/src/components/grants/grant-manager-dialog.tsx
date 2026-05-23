// apps/web/src/components/grants/grant-manager-dialog.tsx
// Sheet-based UI for managing role grants on a single user (platform scope)
// or a single workspace member (workspace scope). Reused by both
// <PlatformUsersPage> and <WorkspaceMembersListPage>. Discriminated by
// `scope`. On grant/revoke success, invalidates the relevant grants list
// AND the parent list (so the granted_role_count badge updates without
// a full page reload).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import type { PlatformRoleGrantOut, WorkspaceRoleGrantOut } from "@xtrusio/api-types";
import {
  deletePlatformRoleGrant,
  deleteWorkspaceRoleGrant,
  errorCode,
  fetchPlatformRoleGrants,
  fetchWorkspaceRoleGrants,
  postPlatformRoleGrant,
  postWorkspaceRoleGrant,
} from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { RolePicker } from "./role-picker";

export type GrantManagerDialogProps =
  | {
      scope: "platform";
      open: boolean;
      userId: string;
      email: string;
      onOpenChange: (open: boolean) => void;
    }
  | {
      scope: "workspace";
      open: boolean;
      workspaceId: string;
      userId: string;
      email: string;
      onOpenChange: (open: boolean) => void;
    };

export function GrantManagerDialog(props: GrantManagerDialogProps) {
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{props.email} — manage roles</SheetTitle>
          <SheetDescription>
            Grant or revoke {props.scope === "platform" ? "platform" : "workspace"} roles for this
            user.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4">
          {props.scope === "platform" ? (
            <PlatformBody userId={props.userId} />
          ) : (
            <WorkspaceBody workspaceId={props.workspaceId} userId={props.userId} />
          )}
        </div>
        <SheetFooter>
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            Close
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function PlatformBody({ userId }: { userId: string }) {
  const qc = useQueryClient();
  const [pickedRoleId, setPickedRoleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const grantsQuery = useQuery({
    queryKey: qk.platformRoleGrants(userId),
    queryFn: () => fetchPlatformRoleGrants(userId),
  });

  const invalidateAll = async () => {
    await qc.invalidateQueries({ queryKey: qk.platformRoleGrants(userId) });
    await qc.invalidateQueries({ queryKey: qk.platformUsers() });
  };

  const grant = useMutation({
    mutationFn: (roleId: string) => postPlatformRoleGrant(userId, roleId),
    onSuccess: async () => {
      await invalidateAll();
      setPickedRoleId(null);
      setError(null);
    },
    onError: (e) => setError(errorMessage(errorCode(e))),
  });

  const revoke = useMutation({
    mutationFn: (grantId: string) => deletePlatformRoleGrant(userId, grantId),
    onSuccess: async () => {
      await invalidateAll();
      setError(null);
    },
    onError: (e) => setError(errorMessage(errorCode(e))),
  });

  const grants = grantsQuery.data?.items ?? [];
  const pending = grant.isPending || revoke.isPending;
  const handleGrant = () => {
    if (!pickedRoleId) return;
    grant.mutate(pickedRoleId);
  };

  return (
    <GrantsBodyInner
      grants={grants}
      onRevoke={(g) => revoke.mutate(g.id)}
      pending={pending}
      error={error}
      picker={
        <RolePicker
          scope="platform"
          value={pickedRoleId}
          onChange={setPickedRoleId}
          disabled={pending}
        />
      }
      onGrant={handleGrant}
      canGrant={pickedRoleId !== null && !pending}
    />
  );
}

function WorkspaceBody({ workspaceId, userId }: { workspaceId: string; userId: string }) {
  const qc = useQueryClient();
  const [pickedRoleId, setPickedRoleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const grantsQuery = useQuery({
    queryKey: qk.workspaceRoleGrants(workspaceId, userId),
    queryFn: () => fetchWorkspaceRoleGrants(workspaceId, userId),
  });

  const invalidateAll = async () => {
    await qc.invalidateQueries({
      queryKey: qk.workspaceRoleGrants(workspaceId, userId),
    });
    await qc.invalidateQueries({
      queryKey: qk.workspaceMembers(workspaceId),
    });
  };

  const grant = useMutation({
    mutationFn: (roleId: string) => postWorkspaceRoleGrant(workspaceId, userId, roleId),
    onSuccess: async () => {
      await invalidateAll();
      setPickedRoleId(null);
      setError(null);
    },
    onError: (e) => setError(errorMessage(errorCode(e))),
  });

  const revoke = useMutation({
    mutationFn: (grantId: string) => deleteWorkspaceRoleGrant(workspaceId, userId, grantId),
    onSuccess: async () => {
      await invalidateAll();
      setError(null);
    },
    onError: (e) => setError(errorMessage(errorCode(e))),
  });

  const grants = grantsQuery.data?.items ?? [];
  const pending = grant.isPending || revoke.isPending;
  const handleGrant = () => {
    if (!pickedRoleId) return;
    grant.mutate(pickedRoleId);
  };

  return (
    <GrantsBodyInner
      grants={grants}
      onRevoke={(g) => revoke.mutate(g.id)}
      pending={pending}
      error={error}
      picker={
        <RolePicker
          scope="workspace"
          workspaceId={workspaceId}
          value={pickedRoleId}
          onChange={setPickedRoleId}
          disabled={pending}
        />
      }
      onGrant={handleGrant}
      canGrant={pickedRoleId !== null && !pending}
    />
  );
}

type GrantLike = PlatformRoleGrantOut | WorkspaceRoleGrantOut;

function GrantsBodyInner({
  grants,
  onRevoke,
  pending,
  error,
  picker,
  onGrant,
  canGrant,
}: {
  grants: GrantLike[];
  onRevoke: (g: GrantLike) => void;
  pending: boolean;
  error: string | null;
  picker: React.ReactNode;
  onGrant: () => void;
  canGrant: boolean;
}) {
  return (
    <div className="space-y-6 py-4">
      <section>
        <h3 className="mb-2 text-sm font-medium text-muted-foreground">Current grants</h3>
        {grants.length === 0 ? (
          <p className="text-sm text-muted-foreground">No roles granted yet.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {grants.map((g) => (
              <li key={g.id} className="flex items-center justify-between gap-2 p-3">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="font-mono">
                    {g.role_key}
                  </Badge>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Revoke ${g.role_key}`}
                  disabled={pending}
                  onClick={() => onRevoke(g)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="space-y-3">
        <h3 className="text-sm font-medium text-muted-foreground">Add a grant</h3>
        {picker}
        <Button onClick={onGrant} disabled={!canGrant} className="w-full">
          {pending ? "Saving…" : "Grant"}
        </Button>
      </section>
      {error ? (
        <p
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
