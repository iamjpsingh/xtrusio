// apps/web/src/components/grants/grant-manager-dialog.tsx
// Sheet-based UI for managing role grants on a single user (platform scope)
// or a single workspace member (workspace scope). Reused by both
// <PlatformUsersPage> and <WorkspaceMembersListPage>. Discriminated by
// `scope`. The grants list + grant/revoke mutations (and the dual cache
// invalidation) live in <ScopedGrantManagerBody>.

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ScopedGrantManagerBody } from "@/components/scoped-grant-manager-body";

export type GrantManagerDialogProps =
  | {
      scope: "platform";
      open: boolean;
      userId: string;
      email: string;
      onOpenChange: (open: boolean) => void;
    }
  | {
      scope: "workspace";
      open: boolean;
      workspaceId: string;
      userId: string;
      email: string;
      onOpenChange: (open: boolean) => void;
    };

export function GrantManagerDialog(props: GrantManagerDialogProps) {
  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent className="flex w-full flex-col gap-0 sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{props.email} — manage roles</SheetTitle>
          <SheetDescription>
            Grant or revoke {props.scope === "platform" ? "platform" : "workspace"} roles for this
            user.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4">
          {props.scope === "platform" ? (
            <ScopedGrantManagerBody scope="platform" userId={props.userId} />
          ) : (
            <ScopedGrantManagerBody
              scope="workspace"
              workspaceId={props.workspaceId}
              userId={props.userId}
            />
          )}
        </div>
        <SheetFooter>
          <Button variant="outline" onClick={() => props.onOpenChange(false)}>
            Close
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
