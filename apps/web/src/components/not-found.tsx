import { Link } from "@tanstack/react-router";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Router-level fallback for any unmatched path. Replaces TanStack's bare
 * "Not Found" text so a genuine 404 is recoverable — "Go home" hits `/`, which
 * redirects to the user's real landing page.
 */
export function NotFound() {
  return (
    <div className="grid min-h-screen place-items-center bg-background px-6 text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="rounded-full bg-muted p-3">
          <Compass className="h-6 w-6 text-muted-foreground" />
        </div>
        <p className="text-sm font-medium tracking-wide text-muted-foreground">404</p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Page not found</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has moved.
        </p>
        <Button asChild className="mt-2">
          <Link to="/">Go to home</Link>
        </Button>
      </div>
    </div>
  );
}
