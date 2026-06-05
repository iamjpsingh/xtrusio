import { useEffect, useMemo, useState } from "react";
import type {
  PermissionDef,
  PermissionScope,
  PlatformRoleOut,
  WorkspaceRoleOut,
} from "@xtrusio/api-types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { PermissionPicker } from "./permission-picker";

type RoleLike = PlatformRoleOut | WorkspaceRoleOut;

export type RoleFormPayload = {
  key: string;
  name: string;
  description: string | null;
  permission_keys: string[];
};

type Props = {
  mode: "create" | "edit";
  role?: RoleLike;
  catalog: PermissionDef[];
  scope: PermissionScope;
  open: boolean;
  pending: boolean;
  error: string | null;
  onSubmit: (payload: RoleFormPayload) => void;
  onOpenChange: (open: boolean) => void;
};

export function RoleFormDialog({
  mode,
  role,
  catalog,
  scope,
  open,
  pending,
  error,
  onSubmit,
  onOpenChange,
}: Props) {
  const [key, setKey] = useState(role?.key ?? "");
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [permissionKeys, setPermissionKeys] = useState<string[]>(role?.permission_keys ?? []);

  // Reset state whenever the dialog is opened with a different role.
  useEffect(() => {
    if (open) {
      setKey(role?.key ?? "");
      setName(role?.name ?? "");
      setDescription(role?.description ?? "");
      setPermissionKeys(role?.permission_keys ?? []);
    }
  }, [open, role]);

  // Count only in-scope selections so the footer matches the picker's total.
  const selectedCount = useMemo(() => {
    const inScope = new Set(catalog.filter((p) => p.scope === scope).map((p) => p.key));
    return permissionKeys.filter((k) => inScope.has(k)).length;
  }, [catalog, scope, permissionKeys]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      key,
      name,
      description: description.trim() === "" ? null : description,
      permission_keys: permissionKeys,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 p-0 sm:max-w-2xl">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader className="shrink-0 border-b p-6">
            <DialogTitle>
              {mode === "create" ? "Create role" : `Edit role — ${role?.name}`}
            </DialogTitle>
            <DialogDescription>
              Bundle permissions into a reusable role you can grant to users.
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="role-name">Name</Label>
                <Input
                  id="role-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Dispatcher"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="role-key" className="text-muted-foreground">
                  Key
                </Label>
                <Input
                  id="role-key"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  pattern="^[a-z][a-z0-9_]*$"
                  disabled={mode === "edit"}
                  className="font-mono text-xs"
                  required
                />
                <p className="text-xs text-muted-foreground">
                  lower_snake_case, e.g. <code>dispatcher</code>
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="role-description">Description (optional)</Label>
              <Textarea
                id="role-description"
                value={description ?? ""}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>

            <PermissionPicker
              catalog={catalog}
              scope={scope}
              value={permissionKeys}
              onChange={setPermissionKeys}
            />
          </div>

          <DialogFooter className="shrink-0 items-center border-t p-6 sm:justify-between">
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {selectedCount} {selectedCount === 1 ? "permission" : "permissions"} selected
            </p>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center">
              {error ? <p className="text-sm text-destructive sm:mr-2">{error}</p> : null}
              <Button
                type="button"
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={pending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={pending}>
                {pending ? "Saving…" : "Save"}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
