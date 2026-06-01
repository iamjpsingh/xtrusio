import { type LucideIcon, RotateCw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

type ErrorStateProps = {
  icon?: LucideIcon;
  title?: string;
  description?: string;
  onRetry?: () => void;
};

/**
 * Shared error surface in the same dashed-card idiom as `EmptyState` /
 * `Forbidden`. When `onRetry` is supplied it renders a "Try again" button —
 * wire it to a query's `refetch` (or a router error-boundary `reset`).
 * Monochrome, tokens only.
 */
export function ErrorState({
  icon: Icon = TriangleAlert,
  title = "Something went wrong",
  description = "We couldn't load this content. Check your connection and try again.",
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card p-8 text-center"
    >
      <div className="rounded-full bg-muted p-3">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <p className="max-w-md text-sm text-muted-foreground">{description}</p>
      {onRetry ? (
        <Button variant="outline" onClick={onRetry} className="mt-2">
          <RotateCw className="h-4 w-4" />
          Try again
        </Button>
      ) : null}
    </div>
  );
}
