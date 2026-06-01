import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type TableSkeletonProps = {
  rows?: number;
  columns?: number;
  /** Optional per-column width classes (e.g. ["w-48", "w-24"]) to echo the
   * real table's column rhythm. Falls back to a sensible default per column. */
  columnWidths?: string[];
};

// Default cell-bar widths cycle so a skeleton reads like real tabular data
// (a wider first column, narrower trailing ones) instead of a uniform grid.
const DEFAULT_WIDTHS = ["w-40", "w-24", "w-16", "w-32", "w-20"];

/**
 * Shaped loading state for any data table. Renders a header row plus `rows`
 * body rows of pulsing `Skeleton` bars that match a table's column rhythm.
 * Monochrome, tokens only — inherits `Skeleton`'s `bg-accent` pulse.
 */
export function TableSkeleton({ rows = 6, columns = 4, columnWidths }: TableSkeletonProps) {
  const widthFor = (col: number) =>
    columnWidths?.[col] ?? DEFAULT_WIDTHS[col % DEFAULT_WIDTHS.length];

  return (
    <Table aria-hidden="true">
      <TableHeader>
        <TableRow>
          {Array.from({ length: columns }).map((_, col) => (
            <TableHead key={col}>
              <Skeleton className={cn("h-4", widthFor(col))} />
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: rows }).map((_, row) => (
          <TableRow key={row}>
            {Array.from({ length: columns }).map((_, col) => (
              <TableCell key={col}>
                <Skeleton className={cn("h-4", widthFor(col))} />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
