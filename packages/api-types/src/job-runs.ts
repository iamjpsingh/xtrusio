// packages/api-types/src/job-runs.ts
//
// Thin re-exports of the generated OpenAPI worker/system job-run schemas, with
// the same `detail` reconciliation the audit-log mirror applies.
//
// RECONCILIATION: the backend types `detail` as `dict[str, Any] | None`, which
// FastAPI emits as an empty-object schema → `openapi-typescript` renders it as
// `Record<string, never> | null`. That's wrong for the runtime shape (it
// carries arbitrary job detail, e.g. `{ errors: [...] }`), so we override it
// back to `Record<string, unknown> | null` here, exactly as `audit-log.ts` does.
//
// Note `id` is a bigint server-side but JSON-serialises as a JS number — fine
// for cursor page sizes well under 2^53.

import type { components } from "../generated/openapi";

type GeneratedJobRun = components["schemas"]["JobRunOut"];

export type JobRunOut = Omit<GeneratedJobRun, "detail"> & {
  detail: Record<string, unknown> | null;
};

type GeneratedJobRunsPage = components["schemas"]["JobRunsPage"];

export type JobRunsPage = Omit<GeneratedJobRunsPage, "items"> & {
  items: JobRunOut[];
};
