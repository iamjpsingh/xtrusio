import { type LucideIcon } from "lucide-react";

type StatCardProps = {
  icon: LucideIcon;
  label: string;
  /** A formatted value, or omit for an intentional "not yet measured" dash. */
  value?: string;
  /** Optional supporting line under the value. */
  hint?: string;
};

/**
 * Compact metric tile for the dashboards. With no `value` it renders a
 * deliberate em-dash placeholder (plus a "Not yet available" hint) so a
 * zero-data dashboard reads as intentional rather than broken. Monochrome,
 * tokens only.
 */
export function StatCard({ icon: Icon, label, value, hint }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums tracking-tight">{value ?? "—"}</p>
      <p className="mt-1 text-xs text-muted-foreground">{hint ?? "Not yet available"}</p>
    </div>
  );
}
