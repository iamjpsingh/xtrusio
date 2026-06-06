// Presentation helpers for the worker/system job-run log.

import type { Badge } from "@/components/ui/badge";

type BadgeVariant = NonNullable<React.ComponentProps<typeof Badge>["variant"]>;

/** Map a job-run status to a Badge variant. */
export function jobStatusVariant(status: string): BadgeVariant {
  switch (status) {
    case "success":
      return "secondary";
    case "partial":
      return "outline";
    case "error":
      return "destructive";
    default:
      return "outline";
  }
}

/** Render a duration in ms as a compact human string: 850ms, 1.2s, 1m 5s. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const totalSec = ms / 1000;
  if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
  const mins = Math.floor(totalSec / 60);
  const secs = Math.round(totalSec % 60);
  return `${mins}m ${secs}s`;
}
