// packages/api-types/src/audit-log.ts
//
// Thin re-exports of the generated OpenAPI audit-log schemas (F.3, finding
// H13), with ONE minimal reconciliation.
//
// RECONCILIATION (generated-vs-mirror mismatch surfaced by codegen):
//   The backend types `before`/`after` as `dict[str, Any] | None`. FastAPI
//   emits this as an empty-object schema, which `openapi-typescript` renders as
//   `Record<string, never> | null` — i.e. "an object that may have NO keys".
//   That is wrong for the runtime shape (these carry arbitrary snapshot data)
//   and breaks every consumer/test that reads real keys out of the JSON.
//   We override those two fields back to `Record<string, unknown> | null` here
//   rather than touch app business logic. The underlying backend imprecision
//   (untyped `dict[str, Any]`) is flagged for follow-up — a typed snapshot
//   model would let this override go away.
//
// Note `id` is a bigint server-side but JSON-serialises as a JS number — fine
// for cursor page sizes well under 2^53.

import type { components } from "../generated/openapi";

type GeneratedAuditEvent = components["schemas"]["AuditEventOut"];

export type AuditEventOut = Omit<GeneratedAuditEvent, "before" | "after"> & {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};

type GeneratedAuditEventsPage = components["schemas"]["AuditEventsPage"];

export type AuditEventsPage = Omit<GeneratedAuditEventsPage, "items"> & {
  items: AuditEventOut[];
};
