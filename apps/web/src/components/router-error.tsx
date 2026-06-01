import type { ErrorRouteComponent } from "@tanstack/react-router";
import { ErrorState } from "@/components/error-state";

/**
 * Router-level error boundary. A thrown query / loader renders this instead of
 * a blank screen. "Try again" calls the boundary's `reset`, which re-runs the
 * failed render — paired with TanStack Query that re-issues the failed fetch.
 */
export const RouterError: ErrorRouteComponent = ({ reset }) => {
  return (
    <div className="p-1">
      <ErrorState onRetry={reset} />
    </div>
  );
};
