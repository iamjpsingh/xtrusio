import { Pencil, Trash2 } from "lucide-react";
import type { PlatformRoleOut, WorkspaceRoleOut } from "@xtrusio/api-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type RoleLike = PlatformRoleOut | WorkspaceRoleOut;

type Props = {
  roles: RoleLike[];
  canManage: boolean;
  onEdit: (r: RoleLike) => void;
  onDelete: (r: RoleLike) => void;
};

export function RolesTable({ roles, canManage, onEdit, onDelete }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Key</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Permissions</TableHead>
          <TableHead className="w-32" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {roles.map((r) => {
          const lock = r.is_system;
          return (
            <TableRow key={r.id}>
              <TableCell className="font-mono text-xs">{r.key}</TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <span>{r.name}</span>
                  {lock ? <Badge variant="secondary">System</Badge> : null}
                </div>
                {r.description ? (
                  <p className="text-xs text-muted-foreground">
                    {r.description}
                  </p>
                ) : null}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {r.permission_keys.length}{" "}
                {r.permission_keys.length === 1 ? "permission" : "permissions"}
              </TableCell>
              <TableCell className="text-right">
                {canManage && !lock ? (
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Edit ${r.key}`}
                      onClick={() => onEdit(r)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${r.key}`}
                      onClick={() => onDelete(r)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ) : null}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
