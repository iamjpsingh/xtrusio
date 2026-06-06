import type { AuditEventOut } from "@xtrusio/api-types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import { diffSnapshots, humanizeField } from "./audit-format";

type Props = {
  event: AuditEventOut | null;
  onOpenChange: (open: boolean) => void;
};

function Leaf({ value }: { value: string | null }) {
  if (value === null) {
    return <span className="text-muted-foreground italic">empty</span>;
  }
  return <span className="font-mono text-xs break-all">{value}</span>;
}

export function AuditDetailDrawer({ event, onOpenChange }: Props) {
  const rows = event ? diffSnapshots(event.before, event.after) : [];
  return (
    <Sheet open={event !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {event?.action_label}
            {event ? (
              <Badge variant="secondary" className="capitalize">
                {event.category}
              </Badge>
            ) : null}
          </SheetTitle>
          <SheetDescription>
            <span className="font-mono text-xs">{event?.action}</span>
            {" · "}
            {event?.actor_email ?? "(system)"}
            {" · "}
            {event ? formatDateTime(event.created_at) : ""}
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-6">
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Target</h3>
            <p className="font-mono text-xs break-all">
              {event?.target_type}:{event?.target_id}
            </p>
          </section>
          <section className="space-y-3">
            <h3 className="text-sm font-medium">Changes</h3>
            {rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No before/after detail recorded for this event.
              </p>
            ) : (
              <div className="overflow-hidden rounded-md border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-muted text-xs text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 font-medium">Field</th>
                      <th className="px-3 py-2 font-medium">Before</th>
                      <th className="px-3 py-2 font-medium">After</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr
                        key={r.field}
                        className={r.changed ? "bg-accent/40" : undefined}
                        data-changed={r.changed}
                      >
                        <td className="px-3 py-2 align-top">{humanizeField(r.field)}</td>
                        <td className="px-3 py-2 align-top">
                          <Leaf value={r.before} />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <Leaf value={r.after} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
