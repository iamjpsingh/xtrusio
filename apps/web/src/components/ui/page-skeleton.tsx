import { Skeleton } from "@/components/ui/skeleton";

/**
 * Generic page-shaped loading state: a header block (title + subtitle bars)
 * over a content slab. Composable — pass children to override the content
 * area, or use the default content block for a quick stand-in. Monochrome,
 * tokens only.
 */
export function PageSkeleton({ children }: { children?: React.ReactNode }) {
  return (
    <div className="space-y-6" aria-hidden="true">
      <div className="space-y-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80" />
      </div>
      {children ?? <Skeleton className="h-64 w-full rounded-lg" />}
    </div>
  );
}

/**
 * Form-shaped loading state for settings / detail pages: a header block over
 * a stack of labeled input rows inside a card. Mirrors the rhythm of a real
 * settings form so the swap to data doesn't shift layout.
 */
export function FormSkeleton({ fields = 3 }: { fields?: number }) {
  return (
    <PageSkeleton>
      <div className="max-w-xl space-y-6 rounded-lg border border-border bg-card p-6">
        {Array.from({ length: fields }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-9 w-full" />
          </div>
        ))}
        <Skeleton className="h-9 w-24" />
      </div>
    </PageSkeleton>
  );
}
