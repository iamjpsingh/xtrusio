import type { JobRunOut } from "@xtrusio/api-types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/format";
import { formatDuration, jobStatusVariant } from "./job-run-format";

type Props = {
  run: JobRunOut | null;
  onOpenChange: (open: boolean) => void;
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{value}</span>
    </div>
  );
}

function errorList(detail: JobRunOut["detail"]): string[] {
  if (!detail) return [];
  const errs = (detail as Record<string, unknown>).errors;
  return Array.isArray(errs) ? errs.map((e) => String(e)) : [];
}

export function JobRunDetailDrawer({ run, onOpenChange }: Props) {
  const errors = run ? errorList(run.detail) : [];
  return (
    <Sheet open={run !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2 font-mono">
            {run?.job_name}
            {run ? (
              <Badge variant={jobStatusVariant(run.status)} className="capitalize">
                {run.status}
              </Badge>
            ) : null}
          </SheetTitle>
          <SheetDescription>{run ? formatDateTime(run.started_at) : ""}</SheetDescription>
        </SheetHeader>
        {run ? (
          <div className="mt-6 space-y-6">
            <section className="divide-y">
              <Row label="Started" value={formatDateTime(run.started_at)} />
              <Row label="Finished" value={formatDateTime(run.finished_at)} />
              <Row label="Duration" value={formatDuration(run.duration_ms)} />
              <Row label="Processed" value={String(run.items_processed)} />
              <Row label="Succeeded" value={String(run.items_succeeded)} />
              <Row label="Failed" value={String(run.items_failed)} />
            </section>
            <section className="space-y-2">
              <h3 className="text-sm font-medium">Errors</h3>
              {errors.length === 0 ? (
                <p className="text-sm text-muted-foreground">No errors recorded for this run.</p>
              ) : (
                <ul className="space-y-1">
                  {errors.map((e, i) => (
                    <li
                      key={i}
                      className="rounded-md border bg-muted p-2 font-mono text-xs break-all"
                    >
                      {e}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
