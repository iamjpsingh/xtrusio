// apps/web/src/components/scoped-grant-manager-body.tsx
// Drains the PlatformBody/WorkspaceBody duplication inside the grant-manager
// dialog (M11). Owns the grants list query + grant/revoke mutations and their
// dual invalidation (grants list + parent list), discriminated by `scope`.

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
import { RolePicker } from "./grants/role-picker";

type GrantLike = PlatformRoleGrantOut | WorkspaceRoleGrantOut;

type Props =
  | { scope: "platform"; userId: string }
  | { scope: "workspace"; workspaceId: string; userId: string };

export function ScopedGrantManagerBody(props: Props) {
  const qc = useQueryClient();
  const [pickedRoleId, setPickedRoleId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const grantsKey =
    props.scope === "platform"
      ? qk.platformRoleGrants(props.userId)
      : qk.workspaceRoleGrants(props.workspaceId, props.userId);

  const grantsQuery = useQuery({
    queryKey: grantsKey,
    queryFn: () =>
      props.scope === "platform"
        ? fetchPlatformRoleGrants(props.userId)
        : fetchWorkspaceRoleGrants(props.workspaceId, props.userId),
  });

  const invalidateAll = async () => {
    await qc.invalidateQueries({ queryKey: grantsKey });
    await qc.invalidateQueries({
      queryKey:
        props.scope === "platform" ? qk.platformUsers() : qk.workspaceMembers(props.workspaceId),
    });
  };

  const grant = useMutation({
    mutationFn: (roleId: string) =>
      props.scope === "platform"
        ? postPlatformRoleGrant(props.userId, roleId)
        : postWorkspaceRoleGrant(props.workspaceId, props.userId, roleId),
    onSuccess: async () => {
      await invalidateAll();
      setPickedRoleId(null);
      setError(null);
    },
    onError: (e) => setError(errorMessage(errorCode(e))),
  });

  const revoke = useMutation({
    mutationFn: (grantId: string) =>
      props.scope === "platform"
        ? deletePlatformRoleGrant(props.userId, grantId)
        : deleteWorkspaceRoleGrant(props.workspaceId, props.userId, grantId),
    onSuccess: async () => {
      await invalidateAll();
      setError(null);
    },
    onError: (e) => setError(errorMessage(errorCode(e))),
  });

  const grants: GrantLike[] = grantsQuery.data?.items ?? [];
  const pending = grant.isPending || revoke.isPending;

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
                  onClick={() => revoke.mutate(g.id)}
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
        {props.scope === "platform" ? (
          <RolePicker
            scope="platform"
            value={pickedRoleId}
            onChange={setPickedRoleId}
            disabled={pending}
          />
        ) : (
          <RolePicker
            scope="workspace"
            workspaceId={props.workspaceId}
            value={pickedRoleId}
            onChange={setPickedRoleId}
            disabled={pending}
          />
        )}
        <Button
          onClick={() => pickedRoleId && grant.mutate(pickedRoleId)}
          disabled={pickedRoleId === null || pending}
          className="w-full"
        >
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
