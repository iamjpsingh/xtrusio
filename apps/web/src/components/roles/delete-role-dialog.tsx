import type { PlatformRoleOut, WorkspaceRoleOut } from "@xtrusio/api-types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

type Props = {
  role: PlatformRoleOut | WorkspaceRoleOut | null;
  pending: boolean;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
};

export function DeleteRoleDialog({
  role,
  pending,
  onConfirm,
  onOpenChange,
}: Props) {
  return (
    <Dialog open={role !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete role — {role?.name}</DialogTitle>
          <DialogDescription>
            This action can't be undone. Anyone currently granted this role
            will lose it (revocation cascades immediately).
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={pending}
          >
            {pending ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
