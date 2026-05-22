import { Link } from "@tanstack/react-router";
import { ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Forbidden({ landingPath }: { landingPath: string }) {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card p-8 text-center">
      <div className="rounded-full bg-muted p-3">
        <ShieldOff className="h-6 w-6 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-semibold tracking-tight">
        You don't have access to this page
      </h2>
      <p className="max-w-md text-sm text-muted-foreground">
        Your account doesn't have permission for this view. If you think that's
        a mistake, ask a workspace owner or platform super admin.
      </p>
      <Button asChild variant="outline" className="mt-2">
        <Link to={landingPath}>Go back</Link>
      </Button>
    </div>
  );
}
