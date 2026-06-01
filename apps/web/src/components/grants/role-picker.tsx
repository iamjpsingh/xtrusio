// apps/web/src/components/grants/role-picker.tsx
// Single-role chooser scoped to either platform or workspace. Wraps
// shadcn <Select> and fetches the role list from the existing P4/P5
// list-roles endpoints. Used by <GrantManagerDialog> when adding a
// new grant to a user / member.

import { useQuery } from "@tanstack/react-query";
import { fetchPlatformRoles, fetchWorkspaceRoles } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const STALE = 60_000;

export type RolePickerProps =
  | {
      scope: "platform";
      value: string | null;
      onChange: (id: string) => void;
      disabled?: boolean;
    }
  | {
      scope: "workspace";
      workspaceId: string;
      value: string | null;
      onChange: (id: string) => void;
      disabled?: boolean;
    };

export function RolePicker(props: RolePickerProps) {
  if (props.scope === "platform") {
    return (
      <PlatformRolePicker
        value={props.value}
        onChange={props.onChange}
        disabled={props.disabled ?? false}
      />
    );
  }
  return (
    <WorkspaceRolePicker
      workspaceId={props.workspaceId}
      value={props.value}
      onChange={props.onChange}
      disabled={props.disabled ?? false}
    />
  );
}

function PlatformRolePicker({
  value,
  onChange,
  disabled,
}: {
  value: string | null;
  onChange: (id: string) => void;
  disabled: boolean;
}) {
  const { data, isLoading } = useQuery({
    queryKey: qk.platformRoles(),
    queryFn: () => fetchPlatformRoles(),
    staleTime: STALE,
  });
  const roles = data?.items ?? [];
  return (
    <PickerInner
      isLoading={isLoading}
      options={roles.map((r) => ({ id: r.id, label: `${r.name} (${r.key})` }))}
      value={value}
      onChange={onChange}
      disabled={disabled}
      ariaLabel="Role"
    />
  );
}

function WorkspaceRolePicker({
  workspaceId,
  value,
  onChange,
  disabled,
}: {
  workspaceId: string;
  value: string | null;
  onChange: (id: string) => void;
  disabled: boolean;
}) {
  const { data, isLoading } = useQuery({
    queryKey: qk.workspaceRoles(workspaceId),
    queryFn: () => fetchWorkspaceRoles(workspaceId),
    staleTime: STALE,
  });
  const roles = data?.items ?? [];
  return (
    <PickerInner
      isLoading={isLoading}
      options={roles.map((r) => ({ id: r.id, label: `${r.name} (${r.key})` }))}
      value={value}
      onChange={onChange}
      disabled={disabled}
      ariaLabel="Role"
    />
  );
}

type Option = { id: string; label: string };

function PickerInner({
  isLoading,
  options,
  value,
  onChange,
  disabled,
  ariaLabel,
}: {
  isLoading: boolean;
  options: Option[];
  value: string | null;
  onChange: (id: string) => void;
  disabled: boolean;
  ariaLabel: string;
}) {
  if (isLoading) {
    return (
      <div role="status" aria-label="Loading roles" className="w-full">
        <Skeleton className="h-9 w-full rounded-md" />
      </div>
    );
  }
  if (options.length === 0) {
    return <p className="text-sm text-muted-foreground">No roles available. Create one first.</p>;
  }
  return (
    <Select value={value ?? undefined} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger aria-label={ariaLabel} className="w-full">
        <SelectValue placeholder="Select a role…" />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.id} value={o.id}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
