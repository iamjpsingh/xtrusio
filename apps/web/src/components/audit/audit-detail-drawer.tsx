import type { AuditEventOut } from "@xtrusio/api-types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

type Props = {
  event: AuditEventOut | null;
  onOpenChange: (open: boolean) => void;
};

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function AuditDetailDrawer({ event, onOpenChange }: Props) {
  return (
    <Sheet open={event !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="font-mono">{event?.action}</SheetTitle>
          <SheetDescription>
            {event?.actor_email ?? "(system)"} —{" "}
            {event ? new Date(event.created_at).toLocaleString() : ""}
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-6">
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Target</h3>
            <p className="font-mono text-xs">
              {event?.target_type}:{event?.target_id}
            </p>
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Before</h3>
            <pre className="max-h-64 overflow-auto rounded-md border bg-muted p-3 font-mono text-xs">
              {event?.before === null || event?.before === undefined
                ? "(none)"
                : pretty(event.before)}
            </pre>
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">After</h3>
            <pre className="max-h-64 overflow-auto rounded-md border bg-muted p-3 font-mono text-xs">
              {event?.after === null || event?.after === undefined
                ? "(none)"
                : pretty(event.after)}
            </pre>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
