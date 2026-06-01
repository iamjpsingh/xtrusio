// apps/web/src/components/scoped-roles-page.tsx
// Generic roles-CRUD page shell shared by the platform and workspace roles
// pages (M11). `platform-roles-page.tsx` and `workspace-roles-page.tsx` are
// thin wrappers over this. The list query + mutations live in
// useScopedRoleCrud; this component owns only the dialog/form UI state.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { errorCode, fetchPermissionsCatalog } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import { useScopedRoleCrud, type RoleScope, type ScopedRole } from "@/hooks/use-scoped-role-crud";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { RolesTable } from "@/components/roles/roles-table";
import { RoleFormDialog, type RoleFormPayload } from "@/components/roles/role-form-dialog";
import { DeleteRoleDialog } from "@/components/roles/delete-role-dialog";

type Props = { scope: RoleScope; workspaceId?: string };

const COPY: Record<RoleScope, { title: string; description: string }> = {
  platform: {
    title: "Platform roles",
    description:
      "Custom platform-scope roles and their permission sets. System roles can't be edited.",
  },
  workspace: {
    title: "Workspace roles",
    description:
      "Custom workspace-scope roles and their permission sets. System roles can't be edited.",
  },
};

export function ScopedRolesPage({ scope, workspaceId }: Props) {
  const { roles, isPending, isError, refetch, create, update, remove } = useScopedRoleCrud(
    scope,
    workspaceId,
  );
  const { data: catalog } = useQuery({
    queryKey: qk.permissionsCatalog(),
    queryFn: fetchPermissionsCatalog,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<ScopedRole | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ScopedRole | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const copy = COPY[scope];

  const onCreate = (p: RoleFormPayload) =>
    create.mutate(p, {
      onSuccess: () => {
        setCreateOpen(false);
        setFormError(null);
      },
      onError: (e) => setFormError(errorMessage(errorCode(e))),
    });

  const onUpdate = (p: RoleFormPayload) => {
    if (!editTarget) return;
    update.mutate(
      { id: editTarget.id, body: p },
      {
        onSuccess: () => {
          setEditTarget(null);
          setFormError(null);
        },
        onError: (e) => setFormError(errorMessage(errorCode(e))),
      },
    );
  };

  const onDelete = () => {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
  };

  const list = isPending ? (
    <TableSkeleton columns={4} columnWidths={["w-32", "w-40", "w-28", "w-20"]} />
  ) : isError ? (
    <ErrorState onRetry={refetch} />
  ) : roles.length === 0 ? (
    <EmptyState
      icon={ShieldCheck}
      title="No custom roles yet"
      description="Create a role to bundle permissions and grant them to users in one step."
    />
  ) : (
    <RolesTable
      roles={roles}
      canManage
      onEdit={(r) => {
        setFormError(null);
        setEditTarget(r as ScopedRole);
      }}
      onDelete={(r) => setDeleteTarget(r as ScopedRole)}
    />
  );

  return (
    <>
      <PageHeader
        title={copy.title}
        description={copy.description}
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
      {list}
      <RoleFormDialog
        mode="create"
        catalog={catalog?.items ?? []}
        scope={scope}
        open={createOpen}
        pending={create.isPending}
        error={formError}
        onSubmit={onCreate}
        onOpenChange={(o) => {
          if (!o) setFormError(null);
          setCreateOpen(o);
        }}
      />
      <RoleFormDialog
        mode="edit"
        role={editTarget ?? undefined}
        catalog={catalog?.items ?? []}
        scope={scope}
        open={editTarget !== null}
        pending={update.isPending}
        error={formError}
        onSubmit={onUpdate}
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
        onConfirm={onDelete}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null);
        }}
      />
    </>
  );
}
