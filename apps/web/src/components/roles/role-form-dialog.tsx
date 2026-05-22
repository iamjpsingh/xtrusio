import { useEffect, useState } from "react";
import type {
  PermissionDef,
  PermissionScope,
  PlatformRoleOut,
  WorkspaceRoleOut,
} from "@xtrusio/api-types";
import {
  Dialog,
  DialogContent,
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
  const [permissionKeys, setPermissionKeys] = useState<string[]>(
    role?.permission_keys ?? [],
  );

  // Reset state whenever the dialog is opened with a different role.
  useEffect(() => {
    if (open) {
      setKey(role?.key ?? "");
      setName(role?.name ?? "");
      setDescription(role?.description ?? "");
      setPermissionKeys(role?.permission_keys ?? []);
    }
  }, [open, role]);

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
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Create role" : `Edit role — ${role?.name}`}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="role-key">Key</Label>
              <Input
                id="role-key"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                pattern="^[a-z][a-z0-9_]*$"
                disabled={mode === "edit"}
                required
              />
              <p className="text-xs text-muted-foreground">
                lower_snake_case, e.g. <code>dispatcher</code>
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role-name">Name</Label>
              <Input
                id="role-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
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
          <div className="space-y-1.5">
            <Label>Permissions</Label>
            <PermissionPicker
              catalog={catalog}
              scope={scope}
              value={permissionKeys}
              onChange={setPermissionKeys}
            />
          </div>
          {error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : null}
          <DialogFooter>
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
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
