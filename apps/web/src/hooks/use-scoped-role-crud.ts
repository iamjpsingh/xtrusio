// apps/web/src/hooks/use-scoped-role-crud.ts
// Drains the ~90%-identical platform/workspace roles-page duplication (M11).
// Owns the roles list query + create/update/delete mutations and their qk
// invalidation, discriminated by `scope`. Consumed by <ScopedRolesPage>.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { PlatformRoleOut, WorkspaceRoleOut } from "@xtrusio/api-types";
import {
  deletePlatformRole,
  deleteWorkspaceRole,
  fetchPlatformRoles,
  fetchWorkspaceRoles,
  patchPlatformRole,
  patchWorkspaceRole,
  postPlatformRole,
  postWorkspaceRole,
} from "@/lib/api";
import { qk } from "@/lib/query-keys";
import type { RoleFormPayload } from "@/components/roles/role-form-dialog";

export type RoleScope = "platform" | "workspace";
export type ScopedRole = PlatformRoleOut | WorkspaceRoleOut;

export function useScopedRoleCrud(scope: RoleScope, workspaceId?: string) {
  const qc = useQueryClient();
  const listKey = scope === "platform" ? qk.platformRoles() : qk.workspaceRoles(workspaceId ?? "");

  const list = useQuery({
    queryKey: listKey,
    queryFn: () =>
      scope === "platform" ? fetchPlatformRoles() : fetchWorkspaceRoles(workspaceId ?? ""),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: listKey });

  const create = useMutation({
    mutationFn: (body: RoleFormPayload): Promise<ScopedRole> =>
      scope === "platform" ? postPlatformRole(body) : postWorkspaceRole(workspaceId ?? "", body),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: RoleFormPayload }): Promise<ScopedRole> =>
      scope === "platform"
        ? patchPlatformRole(id, body)
        : patchWorkspaceRole(workspaceId ?? "", id, body),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      scope === "platform" ? deletePlatformRole(id) : deleteWorkspaceRole(workspaceId ?? "", id),
    onSuccess: invalidate,
  });

  return {
    roles: list.data?.items ?? [],
    isPending: list.isPending,
    isError: list.isError,
    refetch: () => void list.refetch(),
    create,
    update,
    remove,
  };
}

export type UseScopedRoleCrud = ReturnType<typeof useScopedRoleCrud>;
