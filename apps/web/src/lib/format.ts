// apps/web/src/lib/format.ts
// Shared, deterministic date/time formatting. Replaces three local
// `formatDate`/`formatTime` copies that each used a raw
// `new Date(iso).toLocaleString()` (locale- and timezone-volatile output,
// inconsistent null handling). A single fixed `Intl.DateTimeFormat` config
// keeps rendered timestamps consistent across the app and across runs.

/**
 * Fixed formatter: explicit `en-US` locale + UTC timezone so the output is
 * deterministic regardless of the host locale/timezone (and stable in tests).
 * Example: `Jun 5, 2026, 02:30 PM`.
 */
const DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: true,
  timeZone: "UTC",
});

type FormatDateTimeOptions = {
  /** What to render when `iso` is null/empty. Defaults to an em-dash. */
  fallback?: string;
};

/**
 * Format an ISO-8601 timestamp for display. Returns `opts.fallback` (default
 * `"—"`) when `iso` is null/empty, and the same fallback when the timestamp
 * is unparseable (rather than rendering "Invalid Date").
 */
export function formatDateTime(
  iso: string | null | undefined,
  opts?: FormatDateTimeOptions,
): string {
  const fallback = opts?.fallback ?? "—";
  if (!iso) return fallback;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return fallback;
  return DATE_TIME_FORMAT.format(new Date(ts));
}
