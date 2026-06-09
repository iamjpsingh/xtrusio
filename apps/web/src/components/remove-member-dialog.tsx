// apps/web/src/components/remove-member-dialog.tsx
// Confirm dialog for removing a member from a workspace. Mirrors
// <DeleteRoleDialog>. The backend (DELETE /api/workspaces/{wid}/members/{uid})
// is the real gate — owners are protected (409 cannot_remove_owner); this
// dialog surfaces that error if it slips through the row-level hide.

import type { WorkspaceMemberListItem } from "@xtrusio/api-types";
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
  member: WorkspaceMemberListItem | null;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
};

export function RemoveMemberDialog({ member, pending, error, onConfirm, onOpenChange }: Props) {
  return (
    <Dialog open={member !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove member — {member?.email ?? "(deleted user)"}</DialogTitle>
          <DialogDescription>
            This removes their access to this workspace and revokes all of their workspace role
            grants. They can be invited back later.
          </DialogDescription>
        </DialogHeader>
        {error ? (
          <p
            role="alert"
            className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-sm text-destructive"
          >
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={pending}>
            {pending ? "Removing…" : "Remove"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
