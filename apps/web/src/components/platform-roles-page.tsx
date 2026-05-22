import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { PlatformRoleOut } from "@xtrusio/api-types";
import {
  deletePlatformRole,
  errorCode,
  fetchPermissionsCatalog,
  fetchPlatformRoles,
  patchPlatformRole,
  postPlatformRole,
} from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import {
  getDefaultLandingPath,
  hasPlatformPerm,
  useMe,
} from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { RolesTable } from "@/components/roles/roles-table";
import {
  RoleFormDialog,
  type RoleFormPayload,
} from "@/components/roles/role-form-dialog";
import { DeleteRoleDialog } from "@/components/roles/delete-role-dialog";

export function PlatformRolesPage() {
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.roles.manage")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body />;
}

function Body() {
  const qc = useQueryClient();
  const { data: catalog } = useQuery({
    queryKey: qk.permissionsCatalog(),
    queryFn: fetchPermissionsCatalog,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const { data: rolesPage } = useQuery({
    queryKey: qk.platformRoles(),
    queryFn: () => fetchPlatformRoles(),
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<PlatformRoleOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlatformRoleOut | null>(
    null,
  );
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (body: RoleFormPayload) => postPlatformRole(body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformRoles() });
      setCreateOpen(false);
      setFormError(null);
    },
    onError: (e) => setFormError(errorMessage(errorCode(e))),
  });

  const update = useMutation({
    mutationFn: (args: { id: string; body: RoleFormPayload }) =>
      patchPlatformRole(args.id, args.body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformRoles() });
      setEditTarget(null);
      setFormError(null);
    },
    onError: (e) => setFormError(errorMessage(errorCode(e))),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deletePlatformRole(id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformRoles() });
      setDeleteTarget(null);
    },
  });

  return (
    <>
      <PageHeader
        title="Platform roles"
        description="Custom platform-scope roles and their permission sets. System roles can't be edited."
        action={
          <Button
            onClick={() => {
              setFormError(null);
              setCreateOpen(true);
            }}
          >
            Create role
          </Button>
        }
      />
      <RolesTable
        roles={rolesPage?.items ?? []}
        canManage
        onEdit={(r) => {
          setFormError(null);
          setEditTarget(r as PlatformRoleOut);
        }}
        onDelete={(r) => setDeleteTarget(r as PlatformRoleOut)}
      />
      <RoleFormDialog
        mode="create"
        catalog={catalog?.items ?? []}
        scope="platform"
        open={createOpen}
        pending={create.isPending}
        error={formError}
        onSubmit={(p) => create.mutate(p)}
        onOpenChange={(o) => {
          if (!o) setFormError(null);
          setCreateOpen(o);
        }}
      />
      <RoleFormDialog
        mode="edit"
        role={editTarget ?? undefined}
        catalog={catalog?.items ?? []}
        scope="platform"
        open={editTarget !== null}
        pending={update.isPending}
        error={formError}
        onSubmit={(p) =>
          editTarget && update.mutate({ id: editTarget.id, body: p })
        }
        onOpenChange={(o) => {
          if (!o) {
            setFormError(null);
            setEditTarget(null);
          }
        }}
      />
      <DeleteRoleDialog
        role={deleteTarget}
        pending={remove.isPending}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget.id)}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null);
        }}
      />
    </>
  );
}
